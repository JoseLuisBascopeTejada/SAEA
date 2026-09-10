"""Unit tests for backend/app/services/face_recognition.py (TSK-204).

Crops come from the real pipeline: TSK-202 synthetic 1080p image ->
detect_faces -> align_face gives 2 aligned crops of DIFFERENT cartoon
faces. Model loads once per module. No DB, no real faces.
"""

from pathlib import Path

import numpy as np
import pytest

from app.services.alignment import align_face
from app.services.face_detection import detect_faces
from app.services.face_recognition import cosine_similarity, get_embedding

MODEL_PATH = Path(__file__).resolve().parents[2] / "models_data" / "w600k_r50.onnx"
DET_MODEL_PATH = Path(__file__).resolve().parents[2] / "models_data" / "det_2.5g.onnx"
MARGIN = 0.01  # required gap between same-face and cross-face similarity


def _pipeline_crops() -> tuple[np.ndarray, np.ndarray]:
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    faces = detect_faces(img, DET_MODEL_PATH)
    assert len(faces) >= 2
    crop_a = align_face(img, faces[0]["landmarks"])
    crop_b = align_face(img, faces[1]["landmarks"])
    return crop_a, crop_b


@pytest.fixture(scope="module")
def crops() -> tuple[np.ndarray, np.ndarray]:
    return _pipeline_crops()


@pytest.fixture(scope="module")
def embeddings(crops) -> tuple[np.ndarray, np.ndarray]:
    crop_a, crop_b = crops
    return get_embedding(crop_a, MODEL_PATH), get_embedding(crop_b, MODEL_PATH)


def test_embedding_shape_dtype(embeddings):
    emb_a, emb_b = embeddings
    assert emb_a.shape == (512,)
    assert emb_b.shape == (512,)
    assert emb_a.dtype == np.float32


def test_embedding_deterministic(crops):
    crop_a, _ = crops
    assert np.array_equal(
        get_embedding(crop_a, MODEL_PATH), get_embedding(crop_a, MODEL_PATH)
    )


def test_same_crop_similarity_one(crops):
    crop_a, _ = crops
    emb1 = get_embedding(crop_a, MODEL_PATH)
    emb2 = get_embedding(crop_a, MODEL_PATH)
    sim = cosine_similarity(emb1, emb2)
    print(f"\nsame-crop cosine similarity: {sim:.8f}")
    assert sim == pytest.approx(1.0, abs=1e-6)


def test_different_crops_dissimilar(crops, embeddings):
    crop_a, crop_b = crops
    emb_a, emb_b = embeddings
    sim_same = cosine_similarity(emb_a, get_embedding(crop_a, MODEL_PATH))
    sim_cross = cosine_similarity(emb_a, emb_b)
    print(f"\nsame-face similarity:  {sim_same:.8f}")
    print(f"cross-face similarity: {sim_cross:.8f}")
    print(f"gap: {sim_same - sim_cross:.8f} (required margin: {MARGIN})")
    assert sim_cross < sim_same - MARGIN
