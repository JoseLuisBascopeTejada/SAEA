"""Face detection via SCRFD-2.5GF (det_2.5g.onnx, buffalo_m pack).

Loads the raw .onnx file directly with onnxruntime (CPU only) and decodes
the raw stride outputs into bounding boxes + 5 landmarks + confidence
scores, following InsightFace's anchor-generation + distance2bbox +
distance2kps logic.

Model I/O (verified empirically on our file):
  - Input:  (1, 3, 640, 640) float32, RGB, normalized (px - 127.5) / 128.0
  - 9 outputs: 3 scores [N,1], 3 bboxes [N,4], 3 keypoints [N,10]
    for FPN strides [8, 16, 32], 2 anchors per location.
"""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

INPUT_SIZE = (640, 640)  # (width, height)
FEAT_STRIDES = [8, 16, 32]
NUM_ANCHORS = 2
FMC = 3  # feature map count

_SESSIONS: dict[str, ort.InferenceSession] = {}


def _get_session(model_path: str | Path) -> ort.InferenceSession:
    key = str(model_path)
    sess = _SESSIONS.get(key)
    if sess is None:
        sess = ort.InferenceSession(key, providers=["CPUExecutionProvider"])
        _SESSIONS[key] = sess
    return sess


def _preprocess(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Letterbox-resize BGR uint8 image to 640x640 and normalize.

    Returns (blob NCHW float32, det_scale to map coords back).
    """
    img_h, img_w = image.shape[:2]
    in_w, in_h = INPUT_SIZE
    im_ratio = float(img_h) / img_w
    model_ratio = float(in_h) / in_w
    if im_ratio > model_ratio:
        new_h = in_h
        new_w = int(new_h / im_ratio)
    else:
        new_w = in_w
        new_h = int(new_w * im_ratio)
    det_scale = float(new_h) / img_h

    resized = cv2.resize(image, (new_w, new_h))
    det_img = np.zeros((in_h, in_w, 3), dtype=np.uint8)
    det_img[:new_h, :new_w, :] = resized

    blob = (det_img.astype(np.float32) - 127.5) / 128.0
    blob = blob[:, :, ::-1]  # BGR -> RGB
    blob = blob.transpose(2, 0, 1)[np.newaxis, :, :, :]  # HWC -> NCHW
    return np.ascontiguousarray(blob), det_scale


def _anchor_centers(feat_h: int, feat_w: int, stride: int) -> np.ndarray:
    grid = np.stack(np.mgrid[:feat_h, :feat_w][::-1], axis=-1).astype(np.float32)
    centers = (grid * stride).reshape((-1, 2))
    if NUM_ANCHORS > 1:
        centers = np.stack([centers] * NUM_ANCHORS, axis=1).reshape((-1, 2))
    return centers


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    """Greedy IoU NMS. dets: (N, 5) [x1, y1, x2, y2, score]."""
    x1 = dets[:, 0]
    y1 = dets[:, 1]
    x2 = dets[:, 2]
    y2 = dets[:, 3]
    scores = dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= thresh)[0]
        order = order[inds + 1]
    return keep


def detect_faces(
    image: np.ndarray,
    model_path: str | Path,
    det_thresh: float = 0.5,
    nms_thresh: float = 0.4,
) -> list[dict]:
    """Detect faces in a BGR image.

    Args:
        image: BGR ndarray, shape (H, W, 3), dtype uint8, range [0, 255].
        model_path: filesystem path to det_2.5g.onnx.
        det_thresh: minimum confidence to keep a detection.
        nms_thresh: IoU threshold for non-maximum suppression.

    Returns:
        List of {"bbox": [x1, y1, x2, y2], "score": float,
        "landmarks": [[x, y] x5]} in original image pixel coordinates.
        Landmark order: left eye, right eye, nose tip,
        left mouth corner, right mouth corner.
    """
    sess = _get_session(model_path)
    blob, det_scale = _preprocess(image)
    input_name = sess.get_inputs()[0].name
    outputs = sess.run(None, {input_name: blob})

    in_w, in_h = INPUT_SIZE
    all_scores: list[np.ndarray] = []
    all_bboxes: list[np.ndarray] = []
    all_kps: list[np.ndarray] = []

    for idx, stride in enumerate(FEAT_STRIDES):
        # Outputs are already batch-free 2D: [N,1] / [N,4] / [N,10].
        scores = np.asarray(outputs[idx]).ravel()
        bbox_preds = np.asarray(outputs[idx + FMC]) * stride
        kps_preds = np.asarray(outputs[idx + FMC * 2]) * stride

        feat_h, feat_w = in_h // stride, in_w // stride
        centers = _anchor_centers(feat_h, feat_w, stride)

        x1 = centers[:, 0] - bbox_preds[:, 0]
        y1 = centers[:, 1] - bbox_preds[:, 1]
        x2 = centers[:, 0] + bbox_preds[:, 2]
        y2 = centers[:, 1] + bbox_preds[:, 3]
        bboxes = np.stack([x1, y1, x2, y2], axis=-1)

        kps = np.empty((kps_preds.shape[0], 5, 2), dtype=np.float32)
        for j in range(5):
            kps[:, j, 0] = centers[:, 0] + kps_preds[:, j * 2]
            kps[:, j, 1] = centers[:, 1] + kps_preds[:, j * 2 + 1]

        pos = scores >= det_thresh
        all_scores.append(scores[pos])
        all_bboxes.append(bboxes[pos])
        all_kps.append(kps[pos])

    if not all_scores or sum(s.size for s in all_scores) == 0:
        return []

    scores_all = np.concatenate(all_scores)
    bboxes_all = np.concatenate(all_bboxes) / det_scale
    kps_all = np.concatenate(all_kps) / det_scale

    order = scores_all.argsort()[::-1]
    bboxes_all = bboxes_all[order]
    scores_all = scores_all[order]
    kps_all = kps_all[order]

    dets = np.hstack([bboxes_all, scores_all.reshape(-1, 1)])
    keep = _nms(dets, nms_thresh)

    results: list[dict] = []
    for i in keep:
        x1, y1, x2, y2 = (float(v) for v in bboxes_all[i])
        results.append(
            {
                "bbox": [x1, y1, x2, y2],
                "score": float(scores_all[i]),
                "landmarks": [
                    [float(x), float(y)] for x, y in kps_all[i].tolist()
                ],
            }
        )
    return results
