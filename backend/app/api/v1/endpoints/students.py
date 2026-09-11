"""Student enrollment + course roster endpoints (TSK-303).

POST /api/v1/students: enrolls a student with 1-3 single-face reference
photos. Exactly one face per photo is required: 0 faces means nothing to
enroll, and >1 faces is ambiguous (guessing which face is the student risks
a biometric integrity error), so both are 400s. One StudentBiometric row is
stored per valid photo (find_best_match already scans all rows, so extra
rows strictly improve recall).

Atomicity: Student row is added + flushed (never committed) up front for
its id; the single db.commit() happens only after ALL photos succeed. Any
failure rolls back the Student row too.

GET /api/v1/courses/{course_id}/students: roster with no embeddings, ever
(enforced structurally: the response model has no embedding field).
"""

import asyncio
import logging
import time
from pathlib import Path
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.database import Course, Student, StudentBiometric
from app.models.schemas import (
    EnrollResponse,
    RosterResponse,
    RosterStudent,
)
from app.services.alignment import align_face
from app.services.face_detection import detect_faces
from app.services.face_recognition import get_embedding
from app.utils.image_processing import decode_image

logger = logging.getLogger(__name__)

router = APIRouter()

MIN_PHOTOS = 1
MAX_PHOTOS = 3
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def _model_paths() -> tuple[Path, Path]:
    import os

    from app.api.v1.endpoints.attendance import _resolve_model_path

    try:
        return (
            _resolve_model_path(os.environ["MODEL_DETECTION_PATH"]),
            _resolve_model_path(os.environ["MODEL_RECOGNITION_PATH"]),
        )
    except KeyError as exc:
        raise RuntimeError(f"missing required env var: {exc}") from exc


@router.post("/students", response_model=EnrollResponse, status_code=201)
async def enroll_student(
    photos: list[UploadFile] = File(...),
    full_name: str = Form(...),
    course_id: UUID = Form(...),
    db: Session = Depends(get_db),
) -> EnrollResponse:
    if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
        raise HTTPException(
            status_code=400,
            detail=f"expected 1-3 reference photos, got {len(photos)}",
        )
    payloads = [await photo.read() for photo in photos]
    if sum(len(b) for b in payloads) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="photos exceed 8MB total")
    if not full_name.strip():
        raise HTTPException(status_code=400, detail="full_name must not be blank")

    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="course not found")

    try:
        det_path, rec_path = _model_paths()
    except RuntimeError:
        logger.exception("model path configuration error")
        raise HTTPException(status_code=500, detail="inference failed")

    try:
        student = Student(full_name=full_name.strip(), course_id=course_id)
        db.add(student)
        db.flush()  # assigns student.id for the biometric FK; NOT committed

        stored = 0
        for idx, payload in enumerate(payloads):
            try:
                image = decode_image(payload)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"bad photo payload: {exc}"
                ) from exc
            faces = await asyncio.to_thread(detect_faces, image, det_path)
            if len(faces) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"no face detected in reference photo {idx + 1}",
                )
            if len(faces) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"multiple faces in reference photo {idx + 1}; "
                        "reference photos must contain exactly one face"
                    ),
                )
            crop = align_face(image, faces[0]["landmarks"])
            embedding = await asyncio.to_thread(get_embedding, crop, rec_path)
            db.add(
                StudentBiometric(
                    student_id=student.id,
                    embedding=np.asarray(embedding, dtype=np.float32).tolist(),
                )
            )
            stored += 1

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("student enrollment failed")
        raise HTTPException(status_code=500, detail="inference failed")

    return EnrollResponse(
        student_id=student.id,
        full_name=student.full_name,
        course_id=student.course_id,
        embeddings_stored=stored,
    )


@router.get("/courses/{course_id}/students", response_model=RosterResponse)
async def get_roster(
    course_id: UUID,
    db: Session = Depends(get_db),
) -> RosterResponse:
    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="course not found")
    students = (
        db.query(Student).filter_by(course_id=course_id).order_by(Student.full_name).all()
    )
    return RosterResponse(
        students=[
            RosterStudent(student_id=s.id, full_name=s.full_name) for s in students
        ]
    )
