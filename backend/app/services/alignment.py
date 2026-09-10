"""Face alignment to canonical 112x112 crop (TSK-203).

Maps the 5 landmarks from face_detection.py onto the ArcFace canonical
template (insightface/utils/face_align.py `arcface_dst`) using Umeyama's
closed-form similarity transform (Umeyama 1991, DOI: 10.1109/34.88573),
faithfully re-implemented from skimage.transform._geometric._umeyama().

InsightFace trains its recognizer on faces aligned with this exact
least-squares path (skimage SimilarityTransform), NOT with RANSAC-based
estimators such as cv2.estimateAffinePartial2D — using a different
estimator risks misalignment that degrades recognition accuracy.
"""

import cv2
import numpy as np

# Canonical 5-point template in 112x112 space (float32, fractional pixels).
# Order: left eye, right eye, nose, left mouth corner, right mouth corner.
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _similarity_matrix(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Estimate 3x3 similarity transform mapping src -> dst (Umeyama 1991).

    src, dst: (N, 2) float arrays of corresponding points.
    Returns 3x3 homogeneous T with [dx, dy, 1]^T ~= T @ [sx, sy, 1]^T.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    num = src.shape[0]

    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_demean = src - src_mean
    dst_demean = dst - dst_mean

    # Cross-covariance (Eq. 38).
    A = dst_demean.T @ src_demean / num

    # Sign correction (Eq. 39).
    d = np.ones(2, dtype=np.float64)
    if np.linalg.det(A) < 0:
        d[1] = -1.0

    U, S, Vh = np.linalg.svd(A)

    # Rotation (Eq. 40, 43).
    rank = np.linalg.matrix_rank(A)
    T = np.eye(3, dtype=np.float64)
    if rank == 0:
        return np.full_like(T, np.nan)
    elif rank == 1:  # dim - 1
        if np.linalg.det(U) * np.linalg.det(Vh) > 0:
            T[:2, :2] = U @ Vh
        else:
            d_corr = d.copy()
            d_corr[1] = -1.0
            T[:2, :2] = U @ np.diag(d_corr) @ Vh
    else:  # full rank
        T[:2, :2] = U @ np.diag(d) @ Vh

    # Scale (Eq. 41, 42).
    scale = (S @ d) / src_demean.var(axis=0).sum()

    # Translation, then fold scale into the rotation block.
    T[:2, 2] = dst_mean - scale * (T[:2, :2] @ src_mean)
    T[:2, :2] *= scale

    return T


def align_face(
    image: np.ndarray,
    landmarks: list[list[float]],
    image_size: int = 112,
) -> np.ndarray:
    """Align a detected face to a canonical square crop.

    Args:
        image: BGR ndarray, shape (H, W, 3), dtype uint8.
        landmarks: 5 [x, y] points in image coords, ordered
            [left eye, right eye, nose, left mouth, right mouth]
            (same order as face_detection.detect_faces output).
        image_size: output square size (default 112).

    Returns:
        (image_size, image_size, 3) uint8 BGR aligned crop.

    Raises:
        ValueError: on degenerate landmarks (collinear / identical points)
            for which no valid similarity transform exists.
    """
    src = np.asarray(landmarks, dtype=np.float64)
    if src.shape != (5, 2):
        raise ValueError(f"expected 5 landmarks of shape (5, 2), got {src.shape}")
    dst = (ARCFACE_TEMPLATE.astype(np.float64)) * (image_size / 112.0)

    T = _similarity_matrix(src, dst)
    if np.any(np.isnan(T)):
        raise ValueError("degenerate landmarks: cannot estimate similarity transform")

    M = T[:2, :]
    return cv2.warpAffine(image, M, (image_size, image_size), borderValue=0.0)
