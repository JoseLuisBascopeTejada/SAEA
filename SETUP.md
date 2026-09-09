# Manual Setup — SAEA (step by step)

These steps assume Linux/macOS. Windows: use WSL2 and follow the Linux steps inside it.

## 1. Docker + Docker Compose

- Install Docker Desktop (macOS/Windows) or Docker Engine (Linux) from the official docs for your OS.
- Verify: `docker --version` and `docker compose version` both print a version number.

## 2. Python 3.11

- Install `pyenv` (or your OS package manager's Python 3.11).
- `pyenv install 3.11.9 && pyenv local 3.11.9` (run inside the repo root, or inside `backend/`).
- Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`.
- Verify: `python --version` prints `Python 3.11.x`.

## 3. Node.js 20 LTS + pnpm

- Install Node 20 LTS via `nvm`: `nvm install 20 && nvm use 20`.
- Enable pnpm via corepack (ships with Node ≥ 16.13): `corepack enable && corepack prepare pnpm@latest --activate`.
- Verify: `pnpm --version` prints a version number.
- From now on, every frontend command is `pnpm ...` — never `npm ...` or `yarn ...`.

## 4. opencode CLI

- Follow the official opencode installation instructions for your platform (check their current docs/site, since install commands change over time).
- Verify it runs: `opencode --version` (or the equivalent check command opencode documents).
- Configure it to point at the free/low-cost model you plan to use, per opencode's own configuration docs.

## 5. Clone and prepare the repo

```bash
git clone <your-repo-url> SAEA
cd SAEA
cp .env.example .env
```

Edit `.env` and replace `POSTGRES_PASSWORD` and `JWT_SECRET_KEY` with real random values, e.g.:

```bash
openssl rand -hex 32
```

## 6. First boot check (before letting the agent touch anything)

```bash
docker compose up -d db
docker compose ps        # db should show "healthy"
docker compose down
```

If this fails, fix Docker networking/permissions before starting Prompt 0 in `PROMPTS.md` — do not ask the coding agent to debug your local Docker install, it has no visibility into your host.

## 7. Give the agent the files

Copy all the `.md` files (`constitution.md`, `spec.md`, `tasks.md`, `agents.md`, `plan.md`, `architecture.md`, `test.md`), plus `README.md`, `.env.example`, `docker-compose.yml`, `Makefile`, `.gitignore`, `CONTRIBUTING.md`, `CHANGELOG.md`, into the repo root, commit them, then open opencode in that repo folder and start with **Prompt 0** from `PROMPTS.md`.