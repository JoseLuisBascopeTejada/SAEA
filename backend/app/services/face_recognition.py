"""Face embedding extraction via ArcFace ResNet50 (w600k_r50.onnx).

Loads the raw .onnx file directly with onnxruntime (CPU only), following
InsightFace's ArcFaceONNX.get_feat() path:
  - Input: 112x112 BGR aligned crop (output of align_face), uint8.
  - Preprocess: BGR->RGB, (px - 127.5) / 127.5, HWC->NCHW float32.
    NOTE: /127.5 here, NOT /128.0 as in the SCRFD detector. Verified
    empirically against our file (no Sub/Mul prefix in first 8 graph nodes).
  - Single forward pass, no flip-test augmentation.
  - Output: raw 512-d embedding (NOT L2-normalized — matches InsightFace,
    which normalizes only at comparison time in compute_sim).
"""

from pathlib import Path

import numpy as np
import onnxruntime as ort

INPUT_SIZE = (112, 112)  # (width, height)
INPUT_MEAN = 127.5
INPUT_STD = 127.5
EMBEDDING_DIM = 512

_SESSIONS: dict[str, ort.InferenceSession] = {}


def _get_session(model_path: str | Path) -> ort.InferenceSession:
    key = str(model_path)
    sess = _SESSIONS.get(key)
    if sess is None:
        sess = ort.InferenceSession(key, providers=["CPUExecutionProvider"])
        _SESSIONS[key] = sess
    return sess


def get_embedding(
    aligned_crop: np.ndarray,
    model_path: str | Path,
) -> np.ndarray:
    """Extract a raw 512-d embedding from a 112x112 aligned BGR crop.

    Args:
        aligned_crop: BGR ndarray, shape (112, 112, 3), dtype uint8.
        model_path: filesystem path to w600k_r50.onnx.

    Returns:
        (512,) float32 ndarray, raw (not L2-normalized).
    """
    sess = _get_session(model_path)
    rgb = aligned_crop[:, :, ::-1].astype(np.float32)
    blob = ((rgb - INPUT_MEAN) / INPUT_STD).transpose(2, 0, 1)[np.newaxis, :, :, :]
    blob = np.ascontiguousarray(blob, dtype=np.float32)
    input_name = sess.get_inputs()[0].name
    net_out = sess.run(None, {input_name: blob})[0]
    return np.asarray(net_out[0], dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity, mirroring InsightFace's ArcFaceONNX.compute_sim."""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
