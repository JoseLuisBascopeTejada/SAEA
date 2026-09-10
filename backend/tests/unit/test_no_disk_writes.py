"""Disk-write guard (TSK-205, constitution.md Article 2.1).

Patches every file-write entry point during a full 3-photo burst and fails
if any of them is invoked in write mode. Scope is deliberately "anywhere on
disk", stricter than tasks.md's "temp/media directory" wording, because
Article 2.1 forbids raw-photo writes anywhere.

Legitimate I/O that must keep working (and does — verified by these tests
passing): read-only opens, .onnx model loads (warmed up OUTSIDE the patch
window), cv2.imencode (RAM-only, never patched), stdout/stderr, DB writes
(outside the patch window).
"""

import builtins
import io
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

from app.utils.image_processing import process_single_image

DET_PATH = Path(__file__).resolve().parents[2] / "models_data" / "det_2.5g.onnx"
REC_PATH = Path(__file__).resolve().parents[2] / "models_data" / "w600k_r50.onnx"

_WRITE_MODES = ("w", "a", "x", "+")


def _burst_photos() -> list[bytes]:
    """3 WebP-encoded synthetic photos (the RF-01 burst), built in RAM."""
    from tests.unit.test_face_detection import make_synthetic_1080p

    photos = []
    for _ in range(3):
        img = make_synthetic_1080p()
        ok, buf = cv2.imencode(".webp", img)
        assert ok
        photos.append(buf.tobytes())
    return photos


class _WriteGuard:
    """Collects write-mode file operations instead of performing them."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self._real_open = builtins.open

    def _guarded_open(self, file, mode="r", *args, **kwargs):
        if isinstance(mode, str) and any(m in mode for m in _WRITE_MODES):
            self.violations.append(f"open({file!r}, mode={mode!r})")
            raise AssertionError(f"disk write blocked: open({file!r}, {mode!r})")
        return self._real_open(file, mode, *args, **kwargs)

    def _record(self, name: str):
        def _inner(*args, **kwargs):
            self.violations.append(f"{name}(args={args!r})")
            return False

        return _inner

    def patches(self):
        patches = [
            mock.patch("builtins.open", self._guarded_open),
            mock.patch("io.open", self._guarded_open),
            mock.patch("cv2.imwrite", self._record("cv2.imwrite")),
            mock.patch("numpy.save", self._record("numpy.save")),
            mock.patch("numpy.savez", self._record("numpy.savez")),
            mock.patch("numpy.savetxt", self._record("numpy.savetxt")),
            mock.patch(
                "tempfile.NamedTemporaryFile",
                self._record("tempfile.NamedTemporaryFile"),
            ),
            mock.patch("tempfile.mkstemp", self._record("tempfile.mkstemp")),
            mock.patch("tempfile.mkdtemp", self._record("tempfile.mkdtemp")),
            mock.patch(
                "tempfile.TemporaryFile", self._record("tempfile.TemporaryFile")
            ),
        ]
        try:
            import PIL.Image  # noqa: F401

            patches.append(
                mock.patch("PIL.Image.Image.save", self._record("PIL.Image.save"))
            )
        except ImportError:
            pass  # PIL is not a backend dependency; nothing to patch
        return patches


@pytest.fixture(scope="module")
def warmed_models():
    """Init ORT sessions once, OUTSIDE any patch window (model reads OK)."""
    from tests.unit.test_face_detection import make_synthetic_1080p

    img = make_synthetic_1080p()
    ok, buf = cv2.imencode(".webp", img)
    assert ok
    faces = process_single_image(buf.tobytes(), DET_PATH, REC_PATH)
    assert len(faces) >= 1  # pipeline really runs; test below is not vacuous


def test_burst_writes_nothing_to_disk(warmed_models):
    photos = _burst_photos()
    guard = _WriteGuard()
    with ExitStack() as stack:
        for p in guard.patches():
            stack.enter_context(p)
        total_faces = 0
        for photo in photos:
            total_faces += len(process_single_image(photo, DET_PATH, REC_PATH))
    assert total_faces >= 1, "pipeline ran but detected no faces (vacuous test)"
    assert guard.violations == [], f"disk writes detected: {guard.violations}"


def test_guard_catches_write(tmp_path):
    """Negative control: prove the guard actually records a write attempt."""
    guard = _WriteGuard()
    target = str(tmp_path / "probe.webp")
    with ExitStack() as stack:
        for p in guard.patches():
            stack.enter_context(p)
        cv2.imwrite(target, np.zeros((8, 8, 3), dtype=np.uint8))
    assert guard.violations != [], "guard failed to record cv2.imwrite"
    assert any("cv2.imwrite" in v for v in guard.violations)
    assert not Path(target).exists()
