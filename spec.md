# Technical Specification (SPEC) — SAEA

Status: draft v0.1
Governs: what the system does. If something is not written here, the agent must not implement it — ask first.

## 1. Scope

A prototype that lets a teacher take classroom attendance by capturing a burst of 3 photos of the classroom. The backend detects faces, matches them against enrolled students, and returns a pre-filled attendance list that the teacher confirms with one tap per student.

Out of scope for v0.1 (do not implement unless a task explicitly asks): student self-enrollment via public link, multi-school tenancy, mobile native app, SMS/email notifications.

## 2. Functional Requirements

- **RF-01 Burst capture**: The PWA captures 3 consecutive photos, 500ms apart, and sends them as a single `multipart/form-data` request.
- **RF-02 Detection & alignment**: Backend detects faces using SCRFD-2.5GF (`det_2.5g`, ONNX, from the official InsightFace `buffalo_m` pack) and aligns each detected face to a 112×112 px crop using the 5 facial landmarks (affine transform).
- **RF-03 Embedding & matching**: Generate a 512-d embedding per aligned face using ArcFace ResNet50 (`w600k_r50`, fp32 ONNX, as distributed in the official InsightFace `buffalo_m` pack — see decision note below). Run cosine similarity search against `pgvector` with threshold ≥ 0.42. Highest score above threshold wins; ties go to "unrecognized".

> **Model pack decision (supersedes the original "MobileFaceNet INT8" plan)**: research during TSK-201 planning found that InsightFace does not distribute a single official pack combining SCRFD-2.5GF with MobileFaceNet — that exact detector ships bundled with ResNet50 in the `buffalo_m` pack instead. We chose `buffalo_m` (SCRFD-2.5GF + ResNet50@WebFace600K) for accuracy, accepting the extra CPU cost vs. MobileFaceNet. No INT8 quantization is applied — models run at their distributed fp32 precision. This changes the latency risk noted in `plan.md`; TSK-502's benchmark is the gate that confirms Article 3.1 of `constitution.md` (5.0s / 50 faces) still holds with the heavier recognizer.
- **RF-04 Teacher verification**: The teacher sees the pre-filled list (name + confidence score) and can toggle each student's status (PRESENT / ABSENT / LATE) with one tap. Nothing is saved to the `attendance` table until the teacher taps "Confirm".
- **RF-05 Offline queue**: If the network is unavailable, the burst and the confirmed attendance are queued in IndexedDB and retried automatically when connectivity returns.

## 3. API Endpoints (FastAPI)

### POST /api/v1/attendance/process-burst
- Request: `multipart/form-data`
  - `photos`: array of 3 WebP images (max 8MB total)
  - `course_id`: UUID (required)
- Response `200 OK`:
```json
{
  "session_id": "uuid",
  "detected_students": [
    { "student_id": "uuid", "name": "Jane Doe", "confidence": 0.89, "suggested_status": "PRESENT" }
  ],
  "unrecognized_count": 2,
  "processing_time_ms": 420
}
```
- Errors: `400` (bad payload/wrong file count), `422` (validation), `500` (inference failure — must include a generic message, never a stack trace, to the client; full stack trace goes to server logs only).

### POST /api/v1/attendance/confirm
- Request body (JSON): `{ "session_id": "uuid", "confirmations": [{ "student_id": "uuid", "status": "PRESENT|ABSENT|LATE" }] }`
- Response `200 OK`: `{ "saved": true, "attendance_record_ids": ["uuid", ...] }`

### POST /api/v1/students
- Enrolls a student and stores their embedding(s). Request: student metadata + 1-3 reference photos (same detect→align→embed pipeline, images discarded after processing per Article 2 of the constitution).

### GET /api/v1/courses/{course_id}/students
- Returns the roster for a course (no embeddings in the response body, ever).

## 4. Database Schema (PostgreSQL 16 + pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE students (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name TEXT NOT NULL,
  course_id UUID NOT NULL REFERENCES courses(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE student_biometrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  embedding VECTOR(512) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON student_biometrics USING hnsw (embedding vector_cosine_ops);

CREATE TABLE courses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL
);

CREATE TABLE attendance_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID NOT NULL REFERENCES students(id),
  course_id UUID NOT NULL REFERENCES courses(id),
  status TEXT NOT NULL CHECK (status IN ('PRESENT','ABSENT','LATE')),
  session_id UUID NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 5. PWA Requirements

- Framework: React + Vite + TypeScript, packaged with `vite-plugin-pwa`.
- Package manager: **pnpm only**.
- Must work offline for: viewing the roster, queuing a burst capture, queuing confirmations.
- State management: a single Zustand (or React Context, pick ONE and document the choice in `architecture.md` before coding) store in `src/store/attendanceStore.ts`.

## 6. Acceptance Criteria for the Prototype (v0.1 "done")

- [ ] `docker compose up` starts Postgres+pgvector and the backend without manual steps.
- [ ] `POST /api/v1/attendance/process-burst` returns a valid response for a 3-photo burst in under 5s on CPU for ≤50 faces.
- [ ] Teacher can confirm attendance and see it persisted in `attendance_records`.
- [ ] No raw photo ever touches disk (verified by a test in `test.md`).
- [ ] PWA works with the network disabled for capture + queued confirm.