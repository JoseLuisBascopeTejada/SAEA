"""Integration tests for biometrics_repo (TSK-204).

Requires the `db` service healthy. Uses synthetic 512-d vectors only
(constitution.md Article 2.3). Tables are ensured idempotently via
Base.metadata.create_all; rows use random UUIDs and are deleted in teardown.
"""

import uuid

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.db.repositories.biometrics_repo import (
    add_biometric,
    find_best_match,
)
from app.db.session import engine
from app.models.database import Base, Course, Student, StudentBiometric


@pytest.fixture()
def db() -> Session:
    from sqlalchemy.orm import sessionmaker

    Base.metadata.create_all(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    created_ids: list[tuple] = []
    session._tsk204_created = created_ids  # type: ignore[attr-defined]
    yield session
    for biometric_id, student_id, course_id in created_ids:
        session.query(StudentBiometric).filter_by(id=biometric_id).delete()
        session.query(Student).filter_by(id=student_id).delete()
        session.query(Course).filter_by(id=course_id).delete()
    session.commit()
    session.close()


def _make_student(db: Session) -> uuid.UUID:
    course = Course(name="TSK-204 probe course")
    db.add(course)
    db.flush()
    student = Student(full_name="Probe Student", course_id=course.id)
    db.add(student)
    db.flush()
    db._tsk204_created.append((None, student.id, course.id))  # type: ignore[attr-defined]
    return student.id


def test_identical_embedding_matches(db: Session):
    rng = np.random.default_rng(204)
    vec = rng.standard_normal(512).astype(np.float32)
    vec /= np.linalg.norm(vec)

    student_id = _make_student(db)
    record = add_biometric(db, student_id, vec)
    db._tsk204_created[-1] = (record.id, student_id, db._tsk204_created[-1][2])  # type: ignore[attr-defined]

    match = find_best_match(db, vec)
    assert match is not None
    print(f"\nidentical-query similarity: {match['similarity']:.8f}")
    assert match["student_id"] == student_id
    assert match["similarity"] == pytest.approx(1.0, abs=1e-6)


def test_unrelated_embedding_no_match(db: Session):
    rng = np.random.default_rng(205)
    stored = rng.standard_normal(512).astype(np.float32)
    stored /= np.linalg.norm(stored)

    student_id = _make_student(db)
    record = add_biometric(db, student_id, stored)
    db._tsk204_created[-1] = (record.id, student_id, db._tsk204_created[-1][2])  # type: ignore[attr-defined]

    rng2 = np.random.default_rng(999)
    query = rng2.standard_normal(512).astype(np.float32)
    query /= np.linalg.norm(query)

    match = find_best_match(db, query)
    print(f"\nunrelated-query match: {match}")
    assert match is None
