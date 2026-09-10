"""Biometrics repository: store embeddings, cosine-similarity search.

Embeddings are stored raw (not L2-normalized), matching InsightFace's
ArcFaceONNX.get() which returns the raw 512-d vector. Normalization happens
at comparison time: pgvector's <=> (cosine distance) computes
1 - cosine_similarity internally, so the 0.42 similarity threshold from
spec.md RF-03 behaves correctly on raw vectors.
"""

import uuid

import numpy as np
from sqlalchemy.orm import Session

from app.models.database import StudentBiometric

SIMILARITY_THRESHOLD = 0.42


def add_biometric(
    db: Session,
    student_id: uuid.UUID,
    embedding: np.ndarray,
) -> StudentBiometric:
    """Persist a raw 512-d embedding for a student."""
    record = StudentBiometric(
        student_id=student_id,
        embedding=np.asarray(embedding, dtype=np.float32).tolist(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def find_best_match(
    db: Session,
    query_embedding: np.ndarray,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict | None:
    """Return the closest stored embedding above threshold, else None.

    Returns {"student_id", "biometric_id", "similarity"} where
    similarity = 1 - cosine_distance, or None if no row scores >= threshold.
    """
    query = np.asarray(query_embedding, dtype=np.float32).tolist()
    dist = StudentBiometric.embedding.cosine_distance(query)
    row = db.query(StudentBiometric, dist.label("distance")).order_by("distance").first()
    if row is None:
        return None
    record, distance = row
    similarity = 1.0 - float(distance)
    if similarity < threshold:
        return None
    return {
        "student_id": record.student_id,
        "biometric_id": record.id,
        "similarity": similarity,
    }
