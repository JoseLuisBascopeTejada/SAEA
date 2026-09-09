# Task Breakdown (TASKS) — SAEA

Rule: the agent implements ONE unchecked task per session, in order, respecting `Depends on`. Never skip ahead. After finishing a task, stop and report which acceptance criteria passed/failed — do not start the next task in the same turn.

Hat = which role from `agents.md` the agent should "wear" mentally for this task (still the same agent/session).

## Phase 1 — Environment & Database

- [x] **TSK-101** — Docker Compose skeleton (db + backend + frontend services)
  - Hat: DevOpsAgent
  - Depends on: none
  - Files: `docker-compose.yml`, `.env.example`, `backend/docker/Dockerfile`, `frontend/docker/Dockerfile`
  - Acceptance: `docker compose up` starts a healthy `pgvector/pgvector:pg16` container reachable on port 5432.

- [ ] **TSK-102** — Backend skeleton (FastAPI app boots)
  - Hat: AIBackendAgent
  - Depends on: TSK-101
  - Files: `backend/app/main.py`, `backend/requirements/base.txt`, `backend/pyproject.toml`
  - Acceptance: `GET /health` returns `200 {"status":"ok"}` when running inside the backend container.

- [ ] **TSK-103** — DB models + Alembic migration for schema in spec.md §4
  - Hat: DBAgent
  - Depends on: TSK-102
  - Files: `backend/app/models/database.py`, `backend/app/db/migrations/*`
  - Acceptance: `alembic upgrade head` creates `students`, `student_biometrics` (with HNSW index), `courses`, `attendance_records` exactly as in spec.md §4. No extra tables.

## Phase 2 — Computer Vision Pipeline

- [ ] **TSK-201** — Model download script
  - Hat: AIBackendAgent
  - Depends on: TSK-102
  - Files: `backend/scripts/download_models.py`
  - Acceptance: script downloads pinned versions of SCRFD-2.5GF and ArcFace MobileFaceNet INT8 ONNX files into `backend/models_data/`, verifying file checksum before accepting the download.

- [ ] **TSK-202** — Face detection module
  - Hat: AIBackendAgent
  - Depends on: TSK-201
  - Files: `backend/app/services/face_detection.py`, `backend/tests/unit/test_face_detection.py`
  - Acceptance: given a 1080p test image, returns bounding boxes + 5 landmarks per face in <150ms on CPU.

- [ ] **TSK-203** — Face alignment module
  - Hat: AIBackendAgent
  - Depends on: TSK-202
  - Files: `backend/app/services/alignment.py`
  - Acceptance: outputs a 112×112 aligned crop; unit test compares landmark positions against reference within tolerance.

- [ ] **TSK-204** — Embedding extraction + cosine matching against pgvector
  - Hat: AIBackendAgent
  - Depends on: TSK-203, TSK-103
  - Files: `backend/app/services/face_recognition.py`, `backend/app/db/repositories/biometrics_repo.py`
  - Acceptance: given a synthetic embedding already in the DB, a query with the same embedding returns similarity 1.0 and matches; a random unrelated embedding returns no match above 0.42.

- [ ] **TSK-205** — Raw-image-never-touches-disk guard
  - Hat: AIBackendAgent
  - Depends on: TSK-204
  - Files: `backend/app/utils/image_processing.py`, `backend/tests/unit/test_no_disk_writes.py`
  - Acceptance: test asserts no file write syscalls occur while processing a burst (mock/patch `open`, `cv2.imwrite`, etc., and fail the test if called with a path under any temp/media directory).

## Phase 3 — Backend API

- [ ] **TSK-301** — `POST /api/v1/attendance/process-burst`
  - Hat: AIBackendAgent
  - Depends on: TSK-204, TSK-205
  - Files: `backend/app/api/v1/endpoints/attendance.py`, `backend/app/models/schemas.py`
  - Acceptance: matches the exact response shape in spec.md §3; returns within 5s for 50 synthetic faces.

- [ ] **TSK-302** — `POST /api/v1/attendance/confirm`
  - Depends on: TSK-301, TSK-103
  - Acceptance: writes rows into `attendance_records`; rejects unknown `session_id` with 404.

- [ ] **TSK-303** — `POST /api/v1/students` (enrollment) + `GET /api/v1/courses/{id}/students`
  - Depends on: TSK-204
  - Acceptance: enrollment stores embedding only (no photo persisted); roster endpoint never returns embeddings.

## Phase 4 — PWA Frontend (pnpm only)

- [ ] **TSK-401** — Vite + React + TS + pnpm skeleton with `vite-plugin-pwa`
  - Hat: FrontendAgent
  - Depends on: none (can run in parallel with Phase 2/3)
  - Files: `frontend/package.json`, `frontend/vite.config.ts`
  - Acceptance: `pnpm install && pnpm dev` serves the app at `localhost:3000`. `package.json` must contain no npm/yarn lockfile — only `pnpm-lock.yaml`.

- [ ] **TSK-402** — Camera capture hook + burst UI
  - Depends on: TSK-401
  - Files: `frontend/src/hooks/useCamera.ts`, `frontend/src/components/CameraCapture.tsx`
  - Acceptance: captures 3 frames 500ms apart from `navigator.mediaDevices.getUserMedia` and exposes them as Blobs.

- [ ] **TSK-403** — API client + attendance list UI
  - Depends on: TSK-402, TSK-301
  - Files: `frontend/src/api/attendanceClient.ts`, `frontend/src/components/AttendanceList.tsx`
  - Acceptance: posts the burst, renders the returned list with per-student toggle.

- [ ] **TSK-404** — Offline queue (IndexedDB) + service worker sync
  - Depends on: TSK-403
  - Files: `frontend/src/services/offlineSync.ts`, `frontend/src/service-worker.ts`
  - Acceptance: with DevTools "offline" enabled, a capture is queued and auto-syncs when back online.

## Phase 5 — Testing & Performance

- [ ] **TSK-501** — Backend unit + integration test suite wiring
  - Files: `backend/tests/conftest.py`, `backend/pytest.ini`
  - Acceptance: `pytest backend/tests/unit backend/tests/integration` passes, coverage ≥ 85% on `backend/app` (excluding `services/` which needs 100%, per test.md).

- [ ] **TSK-502** — Performance benchmark for burst processing
  - Files: `backend/tests/performance/test_burst_latency.py`
  - Acceptance: asserts p95 latency < 5.0s for a 50-face synthetic burst on CPU.

## Phase 6 — Packaging

- [ ] **TSK-601** — `make dev` / `make prod` end-to-end run
  - Files: `Makefile`
  - Acceptance: fresh clone → `make setup && make dev` → full flow (capture → process → confirm) works with zero manual steps beyond `.env` creation.