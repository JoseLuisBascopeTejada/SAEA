# Agent Configuration (AGENTS) — SAEA

## Operating model: single agent, multiple "hats"

We use **one opencode agent/session**. It is not literally split into multiple parallel agents — that requires more coordination reliability than a free low-capability model can provide. Instead, before each task the agent reads which "hat" (role) applies (see `tasks.md`) and adopts that role's scope and constraints for that task only.

## Hats

### ArchitectAgent
- Responsibility: keep `constitution.md` and `architecture.md` respected. Never write feature code.
- Allowed to touch: `*.md` files at the repo root only.
- Autonomy: may propose changes to architecture; must NOT apply them without human approval (Article 5, constitution.md).

### DBAgent
- Responsibility: schema, migrations, `pgvector` repository queries.
- Allowed to touch: `backend/app/db/`, `backend/app/models/database.py`.
- Must not touch: `backend/app/api/`, `frontend/`.

### AIBackendAgent
- Responsibility: FastAPI endpoints, CV pipeline (detection/alignment/embedding), business logic.
- Allowed to touch: `backend/app/services/`, `backend/app/api/`, `backend/app/utils/`.
- Tools: Python 3.11, ONNX Runtime, OpenCV, pytest. No GPU calls.

### FrontendAgent
- Responsibility: PWA (React + Vite + TS).
- Allowed to touch: `frontend/`.
- Hard rule: **pnpm only**. Any command must be `pnpm ...`. If asked to "npm install X", translate to `pnpm add X` — never run npm.

### DevOpsAgent
- Responsibility: Docker, Compose, Makefile, CI.
- Allowed to touch: `docker-compose.yml`, `*/docker/Dockerfile`, `Makefile`, `.github/workflows/`.

### TestAgent
- Responsibility: writes/maintains tests per `test.md`. Runs after each feature task, not before.

## Workflow per task (mandatory)

1. **Read**: `constitution.md`, `spec.md`, `architecture.md`, and the specific task block in `tasks.md`. Do not read ahead into future tasks.
2. **Plan mode**: produce a short plan — files to touch, function/endpoint signatures, how acceptance criteria will be verified. No implementation code yet.
3. **Human checkpoint**: human approves, edits, or rejects the plan.
4. **Build mode**: implement exactly the approved plan. Run the relevant tests/commands yourself before reporting done.
5. **Report**: state which acceptance criteria passed/failed, with the literal command output. Stop. Do not start the next task.

## Escalation (see also constitution.md Article 4)

If a core-feature bug survives 2 fix attempts:
- Stop.
- Output a report with: task ID, failing criterion, exact command + exact error text, files needed from the human (explicit paths), and what was already tried (max 3 bullets).
- Wait for the human to paste the requested file contents before trying again.

## Things this agent must NEVER do without being asked in the current task

- Modify `constitution.md`, `spec.md`, or `architecture.md`.
- Add a new dependency not listed in the approved plan.
- Use `npm` or `yarn` for anything under `frontend/`.
- Persist raw images to disk anywhere (Article 2 of constitution.md).
- Invent an API response field, DB column, or file path not present in `spec.md`. If something seems missing, ask instead of guessing.