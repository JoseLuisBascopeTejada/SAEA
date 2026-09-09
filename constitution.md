# Constitution — School Attendance Automation System (SAEA)

This document defines non-negotiable rules. No agent (AI) and no human contributor may violate this file. If a task in `tasks.md` conflicts with this file, this file wins and the task must be stopped and reported to the human.

## Article 1 — Development Process

1.1. **Specification First**: No code is written unless it is described in `spec.md` AND broken down into an atomic task in `tasks.md`. If a request has no matching task, STOP and ask the human to add it to `tasks.md` first.

1.2. **One task at a time**: The agent implements exactly one task ID from `tasks.md` per work session. It does not start the next task automatically, even if it seems trivial.

1.3. **Two-phase execution**: Every task follows Plan → Approval → Build:
   - Plan mode: list files to create/modify, function/endpoint signatures, and how you will verify the acceptance criteria. Do NOT write implementation code in this phase.
   - The human approves or edits the plan.
   - Build mode: implement exactly what was approved. Nothing extra.

1.4. **Zero-cost constraint**: Only free, open-source tools and libraries. No paid APIs, no paid model weights, no paid SaaS.

1.5. **CPU-only inference**: The backend must never assume a GPU is present. All AI inference code must run on x86_64 multi-core CPU.

1.6. **Package managers**:
   - Frontend/Node.js: **pnpm only**. Never use `npm install`, `npm run`, or `yarn`. If a tool or docs suggest npm/yarn, translate the command to the pnpm equivalent.
   - Backend/Python: `pip` inside a virtual environment, using the split `requirements/*.txt` files.

## Article 2 — Biometric Privacy (Privacy by Design)

2.1. **No raw photo storage**: Uploaded images (JPEG/PNG/WebP) are processed only in RAM and discarded immediately after inference. Writing raw face photos to disk is forbidden anywhere in the codebase.

2.2. **Embeddings only**: Only 512-dimension numeric embeddings are persisted. These are treated as protected biometric data. No code path may attempt to reconstruct an image from an embedding.

2.3. **Test data**: Automated tests and fixtures must use synthetic embeddings (random L2-normalized 512-d vectors) or public anonymized datasets. Never commit real student photos or real embeddings to the repository.

## Article 3 — Performance Thresholds

3.1. **Latency**: End-to-end processing for a burst of up to 50 students must not exceed 5.0 seconds on CPU.

3.2. **Accuracy**: Face detection F1-score ≥ 0.85 for faces smaller than 32×32 px. Recognition Recall > 95% at the configured similarity threshold.

## Article 4 — Escalation Protocol (mandatory for a low-capability free agent)

4.1. If the agent attempts to fix a bug in a **core feature** (burst capture, detection, alignment, embedding extraction, vector search, attendance confirmation) and fails **twice**, it must STOP immediately. It must NOT try a third fix, NOT rewrite unrelated files, and NOT change the architecture on its own.

4.2. When stopping, the agent must produce a short report containing:
   - The exact task ID and acceptance criterion that is failing.
   - The exact command it ran and the exact error output (verbatim, not summarized).
   - A list of the specific files it needs from the human to continue (by path).
   - What it already tried (max 3 bullet points).

4.3. The human then pastes the requested files/output back into the chat. The agent must not guess file contents instead of asking.

## Article 5 — Change Governance

5.1. Changes to this file, `spec.md`, or `architecture.md` require explicit human approval — the agent may propose a diff but never apply it silently.

5.2. Every merged change must have a corresponding entry in `CHANGELOG.md` under `[Unreleased]`.