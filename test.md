# Testing Strategy (TEST) — SAEA

## Coverage targets

- Backend core (`backend/app`, excluding `services/`): ≥ 85% line coverage.
- AI pipeline (`backend/app/services/`): 100% coverage on preprocessing, alignment, postprocessing functions.
- Frontend PWA critical components: ≥ 75% coverage.

## Test pyramid

1. **Unit** — isolate image transforms, alignment math, and cosine-similarity helpers using synthetic fixtures (no real faces). Location: `backend/tests/unit/`.
2. **Integration** — run FastAPI against a real Postgres+pgvector container (docker), verifying embeddings persist and vector search returns expected matches. Location: `backend/tests/integration/`.
3. **E2E (Playwright)** — simulate the PWA using Chrome flags `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream` with a local Y4M/MJPEG file feeding the fake camera. Location: `frontend/tests/e2e/`.

## Mandatory security/privacy test

`backend/tests/unit/test_no_disk_writes.py` (TSK-205) must patch every file-write entry point (`open`, `cv2.imwrite`, `PIL.Image.save`, `tempfile.*`) during a full burst-processing call and fail if any is invoked with a path that would persist image bytes.

## Commands

- Backend unit + integration: `pytest backend/tests/unit backend/tests/integration`
- Performance benchmark: `pytest backend/tests/performance --benchmark-only`
- Frontend unit: `pnpm --dir frontend test`
- Frontend E2E: `pnpm --dir frontend exec playwright test`

## Model evaluation (not part of CI, run manually before milestone M2 sign-off)

- Detection: adapt the official WIDER FACE validation script against SCRFD-2.5GF outputs.
- Recognition: build FAR/FRR confusion matrices on a LFW subset, plot ROC, confirm the 0.42 threshold is near-optimal for this deployment; adjust `SIMILARITY_THRESHOLD` in `.env` if not, and log the change in `CHANGELOG.md`.

## Camera mocking (frontend unit tests)

Mock `navigator.mediaDevices.getUserMedia` in Jest/Vitest to return a synthetic `MediaStream` bound to an animated `<canvas>`, so `useCamera.ts` can be tested without a real browser camera.