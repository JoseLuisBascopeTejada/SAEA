"""Integration tests for POST /api/v1/attendance/process-burst (TSK-301).

Small burst (3 photos x 2 synthetic faces = 6 faces): correctness only
(response shape, dedup, error codes). The 50-face/<5s performance gate
belongs exclusively to TSK-502 — not asserted here.

Fixture enrolls one student with a REAL pipeline embedding of synthetic
face A, so at least one detection genuinely matches (non-vacuous); the
second synthetic face stays unenrolled (-> unrecognized_count).
"""

import uuid
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.repositories.biometrics_repo import add_biometric
from app.db.session import engine
from app.main import app
from app.models.database import (
    Base,
    AttendanceRecord,
    AttendanceSession,
    Course,
    Student,
    StudentBiometric,
)
from app.services.alignment import align_face
from app.services.face_detection import detect_faces
from app.services.face_recognition import get_embedding

DET_PATH = Path("/app/models_data/det_2.5g.onnx")
REC_PATH = Path("/app/models_data/w600k_r50.onnx")

client = TestClient(app)


def _burst_files() -> list[tuple]:
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    files = []
    for i in range(3):
        # Quality 80: ~209KB/photo (phone-realistic); default is lossless
        # (~3.7MB/photo) which blows the spec's 8MB burst cap. Verified:
        # quality 80 still yields 2 faces at det_thresh=0.5.
        ok, buf = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 80])
        assert ok
        files.append(("photos", (f"p{i}.webp", buf.tobytes(), "image/webp")))
    return files


@pytest.fixture()
def enrolled_course():
    """Course + student enrolled with a real embedding of synthetic face A."""
    Base.metadata.create_all(engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    db = Session()
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    faces = detect_faces(img, DET_PATH)
    assert len(faces) >= 1
    crop_a = align_face(img, faces[0]["landmarks"])
    emb_a = get_embedding(crop_a, REC_PATH)

    course = Course(name="TSK-301 course")
    db.add(course)
    db.flush()
    student = Student(full_name="Enrolled Alice", course_id=course.id)
    db.add(student)
    db.flush()
    record = add_biometric(db, student.id, emb_a)
    course_id, student_id, biometric_id = course.id, student.id, record.id
    db.close()
    yield {"course_id": course_id, "student_id": student_id}
    db2 = Session()
    # Teardown order respects FKs: process_burst now persists
    # attendance_sessions rows referencing the course.
    db2.query(AttendanceRecord).filter_by(course_id=course_id).delete()
    db2.query(AttendanceSession).filter_by(course_id=course_id).delete()
    db2.query(StudentBiometric).filter_by(id=biometric_id).delete()
    db2.query(Student).filter_by(id=student_id).delete()
    db2.query(Course).filter_by(id=course_id).delete()
    db2.commit()
    db2.close()


def test_process_burst_matches_enrolled(enrolled_course):
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=_burst_files(),
        data={"course_id": str(enrolled_course["course_id"])},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    uuid.UUID(body["session_id"])
    assert isinstance(body["processing_time_ms"], int)
    assert isinstance(body["unrecognized_count"], int)
    ids = [s["student_id"] for s in body["detected_students"]]
    assert str(enrolled_course["student_id"]) in ids
    match = next(
        s
        for s in body["detected_students"]
        if s["student_id"] == str(enrolled_course["student_id"])
    )
    assert match["name"] == "Enrolled Alice"
    assert match["confidence"] >= 0.42
    assert match["suggested_status"] == "PRESENT"
    # Same student in all 3 photos appears exactly once (dedup).
    assert ids.count(str(enrolled_course["student_id"])) == 1


@pytest.fixture()
def empty_course():
    """Course with NO enrollments: every detected face is unrecognized."""
    Base.metadata.create_all(engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    db = Session()
    course = Course(name="TSK-301 empty course")
    db.add(course)
    db.commit()
    course_id = course.id
    db.close()
    yield {"course_id": course_id}
    db2 = Session()
    db2.query(AttendanceRecord).filter_by(course_id=course_id).delete()
    db2.query(AttendanceSession).filter_by(course_id=course_id).delete()
    db2.query(Course).filter_by(id=course_id).delete()
    db2.commit()
    db2.close()


def test_process_burst_counts_unrecognized(empty_course):
    # No enrollments -> both cartoon faces are unknown. Their mutual
    # similarity (~0.97, measured in TSK-204) clusters them into ONE
    # unknown identity across all 3 photos: unrecognized_count == 1.
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=_burst_files(),
        data={"course_id": str(empty_course["course_id"])},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["detected_students"] == []
    assert body["unrecognized_count"] == 1


def test_wrong_file_count_400(enrolled_course):
    files = _burst_files()[:2]
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=files,
        data={"course_id": str(enrolled_course["course_id"])},
    )
    assert resp.status_code == 400


def test_garbage_bytes_400(enrolled_course):
    rng = np.random.default_rng(301)
    files = [
        ("photos", (f"g{i}.webp", rng.bytes(1024), "image/webp")) for i in range(3)
    ]
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=files,
        data={"course_id": str(enrolled_course["course_id"])},
    )
    assert resp.status_code == 400


def test_unknown_course_404():
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=_burst_files(),
        data={"course_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
