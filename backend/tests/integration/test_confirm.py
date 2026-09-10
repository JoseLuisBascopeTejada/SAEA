"""Integration tests for POST /api/v1/attendance/confirm (TSK-302).

End-to-end and non-vacuous: burst first (real session_id persisted in
attendance_sessions), then confirm, then verify attendance_records rows
directly in the DB. Rows use real UUIDs and are deleted in teardown.
"""

import uuid

import cv2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

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
from app.db.repositories.biometrics_repo import add_biometric

from pathlib import Path

DET_PATH = Path("/app/models_data/det_2.5g.onnx")
REC_PATH = Path("/app/models_data/w600k_r50.onnx")

client = TestClient(app)
Session = sessionmaker(bind=engine)


def _burst_files() -> list[tuple]:
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    files = []
    for i in range(3):
        ok, buf = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 80])
        assert ok
        files.append(("photos", (f"p{i}.webp", buf.tobytes(), "image/webp")))
    return files


@pytest.fixture()
def enrolled_course():
    """Course + student enrolled with a real embedding of synthetic face A."""
    Base.metadata.create_all(engine, checkfirst=True)
    db = Session()
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    faces = detect_faces(img, DET_PATH)
    assert len(faces) >= 1
    emb_a = get_embedding(align_face(img, faces[0]["landmarks"]), REC_PATH)

    course = Course(name="TSK-302 course")
    db.add(course)
    db.flush()
    student = Student(full_name="Enrolled Bob", course_id=course.id)
    db.add(student)
    db.flush()
    record = add_biometric(db, student.id, emb_a)
    ids = (course.id, student.id, record.id)
    db.close()
    yield {"course_id": ids[0], "student_id": ids[1]}
    db2 = Session()
    db2.query(AttendanceRecord).filter_by(course_id=ids[0]).delete()
    db2.query(AttendanceSession).filter_by(course_id=ids[0]).delete()
    db2.query(StudentBiometric).filter_by(id=ids[2]).delete()
    db2.query(Student).filter_by(id=ids[1]).delete()
    db2.query(Course).filter_by(id=ids[0]).delete()
    db2.commit()
    db2.close()


def _process_burst(course_id) -> dict:
    resp = client.post(
        "/api/v1/attendance/process-burst",
        files=_burst_files(),
        data={"course_id": str(course_id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_process_burst_persists_session(enrolled_course):
    """Criterion 2: session_id is a real DB row, not an in-memory UUID."""
    body = _process_burst(enrolled_course["course_id"])
    db = Session()
    row = db.get(AttendanceSession, body["session_id"])
    assert row is not None
    assert row.course_id == enrolled_course["course_id"]
    assert row.confirmed_at is None
    db.close()


def test_confirm_end_to_end(enrolled_course):
    """Criterion 3: confirm writes records + sets confirmed_at."""
    body = _process_burst(enrolled_course["course_id"])
    sid = body["session_id"]
    assert len(body["detected_students"]) >= 1
    student_id = body["detected_students"][0]["student_id"]

    resp = client.post(
        "/api/v1/attendance/confirm",
        json={"session_id": sid, "confirmations": [{"student_id": student_id, "status": "LATE"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] is True
    assert len(resp.json()["attendance_record_ids"]) == 1

    db = Session()
    rec_id = uuid.UUID(resp.json()["attendance_record_ids"][0])
    rec = db.get(AttendanceRecord, rec_id)
    assert rec is not None
    assert rec.status == "LATE"
    assert str(rec.session_id) == sid
    assert rec.course_id == enrolled_course["course_id"]
    sess = db.get(AttendanceSession, sid)
    assert sess.confirmed_at is not None
    db.close()


def test_confirm_unknown_session_404():
    """Criterion 4."""
    resp = client.post(
        "/api/v1/attendance/confirm",
        json={"session_id": str(uuid.uuid4()), "confirmations": [{"student_id": str(uuid.uuid4()), "status": "PRESENT"}]},
    )
    assert resp.status_code == 404


def test_confirm_double_409(enrolled_course):
    """Criterion 5: second confirm is rejected, rows not duplicated."""
    body = _process_burst(enrolled_course["course_id"])
    sid = body["session_id"]
    student_id = body["detected_students"][0]["student_id"]
    payload = {"session_id": sid, "confirmations": [{"student_id": student_id, "status": "PRESENT"}]}

    first = client.post("/api/v1/attendance/confirm", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/attendance/confirm", json=payload)
    assert second.status_code == 409, second.text

    db = Session()
    count = db.query(AttendanceRecord).filter_by(session_id=uuid.UUID(sid)).count()
    db.close()
    assert count == 1


def test_confirm_unknown_student_404(enrolled_course):
    body = _process_burst(enrolled_course["course_id"])
    resp = client.post(
        "/api/v1/attendance/confirm",
        json={"session_id": body["session_id"], "confirmations": [{"student_id": str(uuid.uuid4()), "status": "PRESENT"}]},
    )
    assert resp.status_code == 404
