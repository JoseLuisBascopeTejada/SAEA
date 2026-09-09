# Prompts for opencode — run these in order

General rules for you (the human):
- Paste ONLY one numbered prompt at a time.
- Before Prompt 1, make sure all the `.md` files from this package are already committed in the repo root, and `backend/`, `frontend/` folders exist (even if empty).
- Every prompt below already tells the agent to use Plan mode first. When it finishes the plan, read it against `spec.md` yourself, then reply with either `Approved, switch to build mode and implement exactly this plan.` or corrections.
- If the agent ever proposes something not in `spec.md`/`tasks.md`, reply: `That is not in spec.md. Do not implement it. Re-read constitution.md Article 1.1 and stop.`
- If the agent shows the Escalation Report (constitution.md Article 4), copy the exact file paths it asks for, open them yourself, and paste their full content back before letting it retry.

---

## Prompt 0 — Bootstrap (paste once, at the start of the very first session)

```
You are working on the SAEA repository using Specification-Driven Development.
Before doing anything else, read these files in this exact order and summarize the
5 most important constraints from each in one bullet point per file:
1. constitution.md
2. architecture.md
3. spec.md
4. agents.md
5. tasks.md

Do not write any code in this turn. Do not propose a plan yet. Just confirm you have
read all five files and list the bullets. Wait for my next message before doing anything else.
```

## Prompt 1 — Start TSK-101 (repeat this pattern for every task)

```
We are starting task TSK-101 from tasks.md. Adopt the "DevOpsAgent" hat described in
agents.md for this task only.

Switch to Plan mode. Do not write implementation files yet.
Read the TSK-101 block in tasks.md and produce a plan listing:
1. Exact files you will create or modify.
2. The exact content structure for docker-compose.yml (services, ports, healthcheck).
3. How you will verify the acceptance criterion ("docker compose up starts a healthy
   pgvector/pgvector:pg16 container reachable on port 5432").

Do not touch any file outside the "Files" list in TSK-101. Do not start any other task.
Stop after presenting the plan and wait for my approval.
```

## Prompt 2 — Approve and build (send after you review the plan)

```
Approved. Switch to Build mode and implement exactly the plan above for TSK-101 only.
After implementing, run the verification command yourself and paste the real output.
Report which acceptance criteria passed or failed using the literal command output,
not a summary. Then stop — do not start TSK-102.
```

## Prompt 3 — Move to the next task

```
TSK-101 is confirmed done. Now start TSK-102 from tasks.md, hat: AIBackendAgent.
Follow the exact same Plan mode → wait for approval → Build mode → report flow as before.
Remember: backend uses pip/venv, never pnpm. Frontend (when we get there) uses pnpm only,
never npm or yarn — this applies for the rest of the project.
```

> Repeat the Prompt 1 → Prompt 2 → Prompt 3 pattern for every remaining task ID in
> `tasks.md`, in order: TSK-103, TSK-201...TSK-205, TSK-301...TSK-303, TSK-401...TSK-404,
> TSK-501, TSK-502, TSK-601. Just swap the task ID and hat name each time.

---

## Prompt template — when a core feature breaks and 2 fixes already failed

```
Stop. Do not attempt a third fix. Follow the Escalation Protocol in constitution.md
Article 4: produce the report with task ID, failing acceptance criterion, exact
command + exact error output, the specific file paths you need from me, and what
you already tried (max 3 bullets). Wait for me to paste those files before continuing.
```

## Prompt template — asking the agent to re-check itself against spec

```
Before continuing, re-read spec.md section for this task's feature and confirm the
current implementation matches it field-by-field (endpoint path, request shape,
response shape, status codes). List any mismatch. Do not fix anything yet, just report.
```

## Prompt template — enforcing pnpm-only after any frontend task

```
Run `ls frontend` and confirm no package-lock.json or yarn.lock file exists — only
pnpm-lock.yaml. If any non-pnpm lockfile exists, delete it and regenerate with
`pnpm install`. Report the result.
```