"""In-RAM image utilities for the attendance pipeline (TSK-205).

Pure functions, no FastAPI imports. TSK-301 (process-burst endpoint) will
import these; all HTTP wiring (multipart parsing, course_id, response
schema) stays in TSK-301.

Privacy: everything here operates in RAM only. No function in this module
may write image bytes to disk (constitution.md Article 2.1). Guarded by
backend/tests/unit/test_no_disk_writes.py.
"""

from pathlib import Path

import cv2
import numpy as np

from app.services.alignment import align_face
from app.services.face_detection import detect_faces
from app.services.face_recognition import get_embedding


def decode_image(data: bytes) -> np.ndarray:
    """Decode WebP/JPEG/PNG bytes to a BGR uint8 ndarray (RAM only).

    Raises:
        ValueError: if data is empty or cannot be decoded as an image.
    """
    if not data:
        raise ValueError("empty image bytes")
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image bytes")
    return img


def process_single_image(
    data: bytes,
    det_path: str | Path,
    rec_path: str | Path,
    det_thresh: float = 0.5,
) -> list[dict]:
    """Full per-photo chain: decode -> detect -> align -> embed.

    Args:
        data: encoded image bytes (WebP/JPEG/PNG).
        det_path: path to det_2.5g.onnx.
        rec_path: path to w600k_r50.onnx.
        det_thresh: detection confidence threshold.

    Returns:
        List of {"bbox", "score", "landmarks", "embedding"} per face.
        "embedding" is a raw (512,) float32 ndarray. Serialization to
        list[float] for API responses is TSK-301's job, not this module's.
    """
    image = decode_image(data)
    results: list[dict] = []
    for face in detect_faces(image, det_path, det_thresh=det_thresh):
        crop = align_face(image, face["landmarks"])
        results.append(
            {
                "bbox": face["bbox"],
                "score": face["score"],
                "landmarks": face["landmarks"],
                "embedding": get_embedding(crop, rec_path),
            }
        )
    return results
