# Contributing to SAEA

## Commit convention (Conventional Commits)

`<type>(<scope>): <description>`

- `feat(ai): add CLAHE normalization before inference`
- `fix(api): fix timeout on burst upload`
- `docs(spec): update endpoint in spec.md`

## Pull request process

1. Branch from `main`: `feature/TSK-ID` or `fix/TSK-ID`.
2. Run `make lint` and `make test` locally — both must pass.
3. PR description must reference the task ID from `tasks.md` and list which acceptance criteria were verified.
4. Request review tagged as `ArchitectAgent` review if `constitution.md`, `spec.md`, or `architecture.md` were touched.

## Frontend rule

Only `pnpm` commands are allowed under `frontend/`. A PR that adds `package-lock.json` or `yarn.lock` will be rejected.
