# Development Plan (PLAN) — SAEA

## Milestones

| Milestone | Description | Phases | Deliverable |
|---|---|---|---|
| M1 | Infra & vector DB | Phase 1 | `docker compose up` gives a working Postgres+pgvector with migrations applied |
| M2 | CV pipeline on CPU | Phase 2 | Script that runs detect→align→embed→match end-to-end on a test image |
| M3 | Backend API | Phase 3 | FastAPI serving attendance endpoints per spec.md §3 |
| M4 | PWA + offline mode | Phase 4 | React app capturing bursts and syncing when offline (pnpm-managed) |
| M5 | Integrated prototype | Phase 5 + 6 | `make prod` runs the full flow end-to-end |

## Definition of Done (per milestone)

A milestone is only "done" when every task in its phase(s) in `tasks.md` is checked AND its acceptance criteria were verified with real command output (not assumed).

## Risk / Mitigation

| Risk | Mitigation |
|---|---|
| Free agent hallucinates file paths or API shapes | Strict "read spec.md before Plan mode" rule (agents.md workflow step 1) |
| Free agent loops on a bug | Escalation Protocol (constitution.md Article 4) — stop after 2 failed attempts |
| CPU inference too slow | TSK-502 benchmark gate before M5; if it fails, reduce burst size or model precision, do not add GPU dependency |
| Frontend drifts to npm/yarn | `pnpm-lock.yaml` is the only lockfile allowed in `frontend/`; any other lockfile in a diff is rejected |