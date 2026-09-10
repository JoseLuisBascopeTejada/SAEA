"""Unit tests for backend/app/services/alignment.py (TSK-203)."""

import numpy as np
import pytest

from app.services.alignment import (
    ARCFACE_TEMPLATE,
    _similarity_matrix,
    align_face,
)
from app.services.face_detection import detect_faces


def test_output_shape():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    lm = [[200.0, 150.0], [400.0, 150.0], [300.0, 250.0],
          [220.0, 350.0], [380.0, 350.0]]
    out = align_face(img, lm)
    assert out.shape == (112, 112, 3)


def test_output_dtype():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    lm = [[200.0, 150.0], [400.0, 150.0], [300.0, 250.0],
          [220.0, 350.0], [380.0, 350.0]]
    out = align_face(img, lm)
    assert out.dtype == np.uint8


def test_matches_umeyama_reference():
    """Verify _similarity_matrix against a known rotation/scale/translation."""
    rng = np.random.default_rng(42)
    pts = rng.random((5, 2)) * 100
    angle = np.deg2rad(30)
    R = np.array([[np.cos(angle), -np.sin(angle)],
                  [np.sin(angle), np.cos(angle)]])
    s = 1.5
    t = np.array([10.0, 20.0])
    transformed = (s * (R @ pts.T).T) + t

    M = _similarity_matrix(pts, transformed)

    for i in range(5):
        proj = M @ np.append(pts[i], 1.0)
        np.testing.assert_allclose(proj[:2], transformed[i], atol=1e-10)

    # Proper rotation, not a reflection.
    assert np.linalg.det(M[:2, :2]) > 0


def test_known_landmarks_centered():
    """Landmarks scaled from the template should map back near the template."""
    scale = 9.0
    offset = np.array([40.0, 30.0])
    img = np.full((1080, 1920, 3), 200, dtype=np.uint8)
    src = (ARCFACE_TEMPLATE.astype(np.float64) * scale + offset).tolist()
    out = align_face(img, src)
    assert out.shape == (112, 112, 3)
    # The whole source image is uniform skin tone, so the aligned crop
    # must be uniformly non-black after mapping back onto the template.
    assert out.mean() > 100.0


def test_zero_landmarks_raises():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        align_face(img, [[0.0, 0.0]] * 5)


def test_identity_like_transform():
    """Source == template on a 112x112 image should reproduce the input."""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(112, 112, 3), dtype=np.uint8)
    out = align_face(img, ARCFACE_TEMPLATE.tolist())
    assert out.shape == (112, 112, 3)
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 2


def test_full_pipeline_detect_then_align():
    """End-to-end: detect on the TSK-202 synthetic image, align the face."""
    from pathlib import Path

    model_path = (
        Path(__file__).resolve().parents[2] / "models_data" / "det_2.5g.onnx"
    )
    img = np.full((1080, 1920, 3), 60, dtype=np.uint8)
    from tests.unit.test_face_detection import _draw_detailed_face

    _draw_detailed_face(img, 550, 500, 460)
    _draw_detailed_face(img, 1370, 500, 460)
    rng = np.random.default_rng(7)
    noise = rng.integers(-12, 13, size=img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    faces = detect_faces(img, model_path)
    assert len(faces) >= 1

    aligned = align_face(img, faces[0]["landmarks"])
    assert aligned.shape == (112, 112, 3)
    assert aligned.dtype == np.uint8
    assert aligned.mean() > 1.0  # not an all-black crop
