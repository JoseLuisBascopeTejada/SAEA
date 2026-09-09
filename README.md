# SAEA — School Attendance Automation System

Prototype for automated school attendance using on-CPU computer vision (face detection + recognition) and vector similarity search.

## Stack

- Backend: FastAPI (Python 3.11) + ONNX Runtime (CPU) + PostgreSQL 16 + pgvector
- Frontend: React + Vite + TypeScript PWA — **package manager: pnpm only**
- Orchestration: Docker Compose

## Prerequisites

See `SETUP.md` for full manual installation steps. Summary:
- Docker + Docker Compose
- Python 3.11
- Node.js 20 LTS + pnpm (via corepack)
- opencode CLI

## Quick start

```bash
git clone <repo-url> && cd SAEA
cp .env.example .env
make setup
make dev
```

Backend docs: http://localhost:8000/docs
Frontend: http://localhost:3000

## Project governance

Read in this order before touching any code: `constitution.md` → `architecture.md` → `spec.md` → `agents.md` → `tasks.md`. See `PROMPTS.md` for the exact prompts to drive the coding agent task by task.

## Makefile commands

- `make setup` — installs backend deps and downloads ONNX models
- `make dev` — runs the full stack via Docker Compose
- `make test` — runs backend + frontend test suites
- `make lint` — runs formatters/linters on both backend and frontend