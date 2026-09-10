"""Unit tests for backend/app/services/face_detection.py (TSK-202).

Test image: synthetic 1920x1080 BGR ndarray generated in-code with OpenCV
(face-like blob). No external files needed. Model: the real
backend/models_data/det_2.5g.onnx (resolved relative to this file, so the
same path works on the host and inside the container via the ./backend:/app
volume mount).
"""

import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import pytest

from app.services.face_detection import detect_faces

MODEL_PATH = Path(__file__).resolve().parents[2] / "models_data" / "det_2.5g.onnx"


_SKIN = (200, 210, 235)  # BGR light skin tone


def _draw_detailed_face(img: np.ndarray, cx: int, cy: int, size: int) -> None:
    """Draw a detailed cartoon face: hair, ears, oval, brows, eyed
    whites+pupils, nose, lips, neck+shirt. Tuned so SCRFD scores it >= 0.5."""
    cv2.ellipse(img, (cx, cy - int(0.12 * size)),
                (int(0.42 * size), int(0.45 * size)), 0, 0, 360, (25, 25, 25), -1)
    cv2.ellipse(img, (cx - int(0.40 * size), cy),
                (int(0.08 * size), int(0.14 * size)), 0, 0, 360, _SKIN, -1)
    cv2.ellipse(img, (cx + int(0.40 * size), cy),
                (int(0.08 * size), int(0.14 * size)), 0, 0, 360, _SKIN, -1)
    cv2.ellipse(img, (cx, cy),
                (int(0.36 * size), int(0.44 * size)), 0, 0, 360, _SKIN, -1)
    cv2.ellipse(img, (cx - int(0.15 * size), cy - int(0.18 * size)),
                (int(0.11 * size), int(0.035 * size)), -10, 0, 360, (30, 30, 30), -1)
    cv2.ellipse(img, (cx + int(0.15 * size), cy - int(0.18 * size)),
                (int(0.11 * size), int(0.035 * size)), 10, 0, 360, (30, 30, 30), -1)
    for sx in (-1, 1):
        ex, ey = cx + sx * int(0.15 * size), cy - int(0.10 * size)
        cv2.ellipse(img, (ex, ey),
                    (int(0.09 * size), int(0.055 * size)), 0, 0, 360, (255, 255, 255), -1)
        cv2.circle(img, (ex, ey), int(0.032 * size), (20, 20, 20), -1)
    cv2.line(img, (cx, cy - int(0.05 * size)),
             (cx - int(0.03 * size), cy + int(0.10 * size)),
             (120, 130, 150), max(2, int(0.015 * size)))
    cv2.circle(img, (cx - int(0.045 * size), cy + int(0.11 * size)),
               int(0.015 * size), (60, 60, 60), -1)
    cv2.circle(img, (cx + int(0.045 * size), cy + int(0.11 * size)),
               int(0.015 * size), (60, 60, 60), -1)
    cv2.ellipse(img, (cx, cy + int(0.22 * size)),
                (int(0.11 * size), int(0.045 * size)), 0, 0, 360, (60, 60, 180), -1)
    cv2.line(img, (cx - int(0.09 * size), cy + int(0.22 * size)),
             (cx + int(0.09 * size), cy + int(0.22 * size)),
             (30, 30, 60), max(2, int(0.012 * size)))
    cv2.rectangle(img, (cx - int(0.12 * size), cy + int(0.44 * size)),
                  (cx + int(0.12 * size), cy + int(0.62 * size)), _SKIN, -1)
    cv2.ellipse(img, (cx, cy + int(0.95 * size)),
                (int(0.42 * size), int(0.35 * size)), 0, 0, 360, (120, 80, 40), -1)


def make_synthetic_1080p() -> np.ndarray:
    img = np.full((1080, 1920, 3), 60, dtype=np.uint8)
    _draw_detailed_face(img, 550, 500, 460)
    _draw_detailed_face(img, 1370, 500, 460)
    # Light fixed-seed sensor noise: breaks up flat fills, deterministic.
    rng = np.random.default_rng(7)
    noise = rng.integers(-12, 13, size=img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def image() -> np.ndarray:
    return make_synthetic_1080p()


@pytest.fixture(scope="module")
def faces(image) -> list:
    return detect_faces(image, MODEL_PATH)


def test_model_loads():
    assert MODEL_PATH.exists(), f"model file missing: {MODEL_PATH}"
    sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    assert sess is not None


def test_output_count_confirmed():
    sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    assert len(sess.get_outputs()) == 9


def test_returns_list(faces):
    assert isinstance(faces, list)


def test_detects_at_least_one_face(faces):
    assert len(faces) >= 1


def test_output_structure(faces):
    for face in faces:
        assert set(face.keys()) == {"bbox", "score", "landmarks"}
        assert isinstance(face["bbox"], list) and len(face["bbox"]) == 4
        assert all(isinstance(v, float) for v in face["bbox"])
        assert isinstance(face["score"], float)
        assert isinstance(face["landmarks"], list)


def test_bbox_bounds(faces, image):
    h, w = image.shape[:2]
    for face in faces:
        x1, y1, x2, y2 = face["bbox"]
        assert 0 <= x1 <= w and 0 <= x2 <= w
        assert 0 <= y1 <= h and 0 <= y2 <= h
        assert x2 > x1 and y2 > y1


def test_scores_valid(faces):
    for face in faces:
        assert 0.0 < face["score"] <= 1.0


def test_exactly_5_landmarks_per_face(faces):
    for face in faces:
        assert len(face["landmarks"]) == 5


def test_landmarks_are_2d_points(faces):
    for face in faces:
        for pt in face["landmarks"]:
            assert isinstance(pt, list) and len(pt) == 2
            assert all(isinstance(v, float) for v in pt)


def test_landmarks_within_bbox(faces):
    margin = 50.0
    for face in faces:
        x1, y1, x2, y2 = face["bbox"]
        for lx, ly in face["landmarks"]:
            assert x1 - margin <= lx <= x2 + margin
            assert y1 - margin <= ly <= y2 + margin


def test_latency_under_150ms(image):
    detect_faces(image, MODEL_PATH)  # warm-up (session init) outside timing
    times_ms = []
    for _ in range(10):
        t0 = time.perf_counter()
        detect_faces(image, MODEL_PATH)
        times_ms.append((time.perf_counter() - t0) * 1000.0)
    median_ms = statistics.median(times_ms)
    print(f"\nlatency runs (ms): {[round(t, 1) for t in times_ms]}")
    print(f"median latency (ms): {median_ms:.1f}")
    assert median_ms < 150.0
