"""POST /api/v1/attendance/process-burst (TSK-301).

Receives a 3-photo WebP burst + course_id, runs the TSK-205 pipeline per
photo, matches each face via biometrics_repo.find_best_match, and merges
detections across photos into one attendance list.

Dedup rule (approved TSK-301 design): recognized detections group by
student_id (keeping the highest detection-score representative, whose match
similarity becomes `confidence`); unmatched detections are greedily
clustered — each is compared against each existing cluster's REPRESENTATIVE
only (the first member's embedding), joining the first cluster with cosine
similarity >= threshold, else starting a new cluster. unrecognized_count =
number of such clusters.
"""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.repositories.biometrics_repo import (
    SIMILARITY_THRESHOLD,
    find_best_match,
)
from app.db.session import get_db
from app.models.database import Course, Student
from app.models.schemas import DetectedStudent, ProcessBurstResponse
from app.services.face_recognition import cosine_similarity
from app.utils.image_processing import process_single_image

logger = logging.getLogger(__name__)

router = APIRouter()

EXPECTED_PHOTOS = 3
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def _model_paths() -> tuple[Path, Path]:
    """Model paths are required env config (no silent default)."""
    try:
        return (
            Path(os.environ["MODEL_DETECTION_PATH"]),
            Path(os.environ["MODEL_RECOGNITION_PATH"]),
        )
    except KeyError as exc:
        raise RuntimeError(f"missing required env var: {exc}") from exc


@router.post("/attendance/process-burst", response_model=ProcessBurstResponse)
async def process_burst(
    photos: list[UploadFile] = File(...),
    course_id: UUID = Form(...),
    db: Session = Depends(get_db),
) -> ProcessBurstResponse:
    t0 = time.perf_counter()

    if len(photos) != EXPECTED_PHOTOS:
        raise HTTPException(
            status_code=400, detail=f"expected 3 photos, got {len(photos)}"
        )
    payloads = [await photo.read() for photo in photos]
    if sum(len(b) for b in payloads) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="burst exceeds 8MB total")

    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="course not found")

    try:
        det_path, rec_path = _model_paths()
    except RuntimeError:
        logger.exception("model path configuration error")
        raise HTTPException(status_code=500, detail="inference failed")

    try:
        all_detections: list[dict] = []
        for payload in payloads:
            try:
                faces = await asyncio.to_thread(
                    process_single_image, payload, det_path, rec_path
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"bad photo payload: {exc}"
                ) from exc
            all_detections.extend(faces)
    except HTTPException:
        raise
    except Exception:
        logger.exception("burst inference failed")
        raise HTTPException(status_code=500, detail="inference failed")

    by_student: dict[UUID, dict] = {}
    unknown_clusters: list[dict] = []
    try:
        for det in all_detections:
            match = find_best_match(db, det["embedding"])
            if match is not None:
                sid = match["student_id"]
                prev = by_student.get(sid)
                if prev is None or det["score"] > prev["_score"]:
                    student = db.get(Student, sid)
                    by_student[sid] = {
                        "student_id": sid,
                        "name": student.full_name,
                        "confidence": match["similarity"],
                        "_score": det["score"],
                    }
            else:
                # Representative-only clustering: compare against each
                # existing cluster's REPRESENTATIVE (first member) only;
                # join the first cluster at similarity >= threshold,
                # otherwise start a new cluster.
                for cluster in unknown_clusters:
                    if (
                        cosine_similarity(
                            det["embedding"], cluster["representative"]
                        )
                        >= SIMILARITY_THRESHOLD
                    ):
                        break
                else:
                    unknown_clusters.append({"representative": det["embedding"]})
    except Exception:
        logger.exception("burst matching failed")
        raise HTTPException(status_code=500, detail="inference failed")

    detected = [
        DetectedStudent(
            student_id=v["student_id"],
            name=v["name"],
            confidence=v["confidence"],
            suggested_status="PRESENT",
        )
        for v in by_student.values()
    ]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ProcessBurstResponse(
        session_id=uuid.uuid4(),
        detected_students=detected,
        unrecognized_count=len(unknown_clusters),
        processing_time_ms=elapsed_ms,
    )
