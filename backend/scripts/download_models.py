#!/usr/bin/env python3
"""Download the InsightFace buffalo_m model pack and copy ONNX files
into backend/models_data/ for direct loading by onnxruntime.

Uses the official insightface PyPI package's own auto-download mechanism.
No hardcoded URLs or checksums — all hosting is delegated to the package.
"""
import shutil
import sys
from pathlib import Path

from insightface.app import FaceAnalysis
from insightface.utils.storage import download as insightface_download

REQUIRED_MODELS = {
    "det_2.5g.onnx": "SCRFD-2.5GF detector",
    "2d106det.onnx": "2D 106-point landmark detector",
    "w600k_r50.onnx": "ArcFace ResNet50 recognizer",
}

MODELS_DATA_DIR = Path(__file__).resolve().parent.parent / "models_data"

ROOT_DIR = Path("/root/.insightface")


def _ensure_pack_downloaded() -> Path:
    """Trigger download of buffalo_m pack and return path to the directory
    that contains the actual .onnx files."""
    pack_dir = ROOT_DIR / "models" / "buffalo_m"

    # insightface's download() returns early if pack_dir already exists.
    # If the dir exists but is empty (e.g. interrupted download, rebuilt
    # container), force re-download.
    force = pack_dir.exists() and not any(pack_dir.iterdir())
    insightface_download("models", "buffalo_m", force=force, root=str(ROOT_DIR))
    nested = pack_dir / "buffalo_m"

    if not nested.is_dir():
        raise FileNotFoundError(
            f"Expected model dir {nested} not found after download"
        )
    return nested


def main() -> int:
    MODELS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Triggering buffalo_m model pack download via insightface ...")
    try:
        model_dir = _ensure_pack_downloaded()
    except Exception as exc:
        print(f"ERROR: Failed to download buffalo_m pack: {exc}", file=sys.stderr)
        return 1

    print(f"Model pack resolved at: {model_dir}")

    # Verify by loading with FaceAnalysis
    print("Verifying models via FaceAnalysis ...")
    try:
        app = FaceAnalysis(name=str(model_dir))
        app.prepare(ctx_id=-1)  # CPU-only (constitution.md Art. 1.5)
        loaded = list(app.models.keys())
        print(f"FaceAnalysis loaded models: {loaded}")
        if "detection" not in loaded:
            print("WARNING: detection model not loaded", file=sys.stderr)
    except Exception as exc:
        print(f"WARNING: FaceAnalysis verification failed: {exc}", file=sys.stderr)

    missing = []
    for filename, description in REQUIRED_MODELS.items():
        src = model_dir / filename
        if not src.exists():
            missing.append((filename, description))
            continue

        dst = MODELS_DATA_DIR / filename
        shutil.copy2(src, dst)
        print(f"Copied {filename} ({description}) -> {dst}")

    if missing:
        print("ERROR: The following model files were not found in the pack:", file=sys.stderr)
        for filename, description in missing:
            print(f"  - {filename} ({description})", file=sys.stderr)
        print(f"Files present in pack dir: {list(model_dir.glob('*.onnx'))}", file=sys.stderr)
        return 1

    print("All models acquired successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
