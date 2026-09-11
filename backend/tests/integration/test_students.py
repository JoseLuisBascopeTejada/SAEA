"""Integration tests for enrollment + roster (TSK-303).

Non-vacuous: enrollments go through the real detect->align->embed pipeline
on synthetic faces, and test_enroll_then_recognize closes the loop by
matching a fresh embedding of the same face against the enrolled student.

Single-face reference photos are tight bbox crops of a detected synthetic
face, re-encoded lossless WebP. Teardown deletes rows FK-order first.
"""

import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.repositories.biometrics_repo import add_biometric, find_best_match
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

from pathlib import Path

DET_PATH = Path("/app/models_data/det_2.5g.onnx")
REC_PATH = Path("/app/models_data/w600k_r50.onnx")

client = TestClient(app)
Session = sessionmaker(bind=engine)


def _fixture_image():
    from tests.unit.test_face_detection import make_synthetic_1080p

    return make_synthetic_1080p()


def _single_face_photo() -> bytes:
    """Padded crop around the first detected synthetic face (exactly 1 face).

    A tight edge-to-edge crop scores ~0.0 (detector needs context); 60%
    padding scores 0.72 at det_thresh=0.5 with exactly 1 face above threshold
    (measured: pad 0.0->0.00, 0.2->0.19, 0.4->0.63, 0.6->0.72, 0.8->0.75).
    """
    img = _fixture_image()
    h, w = img.shape[:2]
    faces = detect_faces(img, DET_PATH)
    assert len(faces) >= 1
    x1, y1, x2, y2 = faces[0]["bbox"]
    bw, bh = x2 - x1, y2 - y1
    pad = 0.6
    px1, py1 = max(0, int(x1 - bw * pad)), max(0, int(y1 - bh * pad))
    px2, py2 = min(w, int(x2 + bw * pad)), min(h, int(y2 + bh * pad))
    crop = img[py1:py2, px1:px2]
    ok, buf = cv2.imencode(".webp", crop)
    assert ok
    return buf.tobytes()


def _two_face_photo() -> bytes:
    img = _fixture_image()
    ok, buf = cv2.imencode(".webp", img)
    assert ok
    return buf.tobytes()


def _noise_photo() -> bytes:
    rng = np.random.default_rng(303)
    noise = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", noise)
    assert ok
    return buf.tobytes()


@pytest.fixture()
def course():
    Base.metadata.create_all(engine, checkfirst=True)
    db = Session()
    c = Course(name="TSK-303 course")
    db.add(c)
    db.commit()
    cid = c.id
    db.close()
    yield {"course_id": cid}
    db2 = Session()
    db2.query(AttendanceRecord).filter_by(course_id=cid).delete()
    db2.query(AttendanceSession).filter_by(course_id=cid).delete()
    for s in db2.query(Student).filter_by(course_id=cid).all():
        db2.query(StudentBiometric).filter_by(student_id=s.id).delete()
        db2.delete(s)
    db2.query(Course).filter_by(id=cid).delete()
    db2.commit()
    db2.close()


def _enroll(course_id, name, photos) -> "object":
    files = [( "photos", (f"r{i}.webp", p, "image/webp")) for i, p in enumerate(photos)]
    return client.post(
        "/api/v1/students",
        files=files,
        data={"full_name": name, "course_id": str(course_id)},
    )


def test_enroll_single_face_photo(course):
    resp = _enroll(course["course_id"], "Enrolled Cara", [_single_face_photo()])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["full_name"] == "Enrolled Cara"
    assert body["embeddings_stored"] == 1

    db = Session()
    try:
        rows = db.query(StudentBiometric).join(
            Student, StudentBiometric.student_id == Student.id
        ).filter(Student.full_name == "Enrolled Cara").all()
        assert len(rows) == 1
        assert len(rows[0].embedding) == 512  # embedding only; photo bytes nowhere
    finally:
        db.close()


def test_enroll_then_recognize(course):
    """Enrollment -> recognition loop closed with a real pipeline embedding."""
    resp = _enroll(course["course_id"], "Enrolled Dan", [_single_face_photo()])
    assert resp.status_code == 201, resp.text
    student_id = resp.json()["student_id"]

    img = _fixture_image()
    faces = detect_faces(img, DET_PATH)
    probe = get_embedding(align_face(img, faces[0]["landmarks"]), REC_PATH)

    db = Session()
    try:
        match = find_best_match(db, probe)
    finally:
        db.close()
    assert match is not None
    assert str(match["student_id"]) == student_id
    assert match["similarity"] >= 0.42


def _student_count(name: str) -> int:
    db = Session()
    try:
        return db.query(Student).filter_by(full_name=name).count()
    finally:
        db.close()


def test_enroll_zero_faces_400(course):
    resp = _enroll(course["course_id"], "Ghost Zero", [_noise_photo()])
    assert resp.status_code == 400, resp.text
    assert _student_count("Ghost Zero") == 0  # atomic: no Student row left behind


def test_enroll_multiple_faces_400(course):
    resp = _enroll(course["course_id"], "Ghost Multi", [_two_face_photo()])
    assert resp.status_code == 400, resp.text
    assert _student_count("Ghost Multi") == 0  # atomic: no Student row left behind


def test_roster_no_embeddings(course):
    _enroll(course["course_id"], "Enrolled Erin", [_single_face_photo()])
    resp = client.get(f"/api/v1/courses/{course['course_id']}/students")
    assert resp.status_code == 200, resp.text
    assert "embedding" not in resp.text  # literal check on the raw body
    names = [s["full_name"] for s in resp.json()["students"]]
    assert "Enrolled Erin" in names
    assert set(resp.json()["students"][0].keys()) == {"student_id", "full_name"}


def test_roster_unknown_course_404():
    resp = client.get(f"/api/v1/courses/{uuid.uuid4()}/students")
    assert resp.status_code == 404
