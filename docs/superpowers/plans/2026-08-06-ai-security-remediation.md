# AI Assistant Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final security review findings before publishing the unified AI portal.

**Architecture:** Keep the existing read-only AI workspace and aggregate-only tool boundary, while enforcing a server-side output policy, distinguishing retryable submission conflicts, resolving scenic names from the effective configuration registry, and coordinating deletion with generation leases. Frontend validation must consume the same route-safe scenic identifier policy as the backend.

**Tech Stack:** FastAPI, SQLAlchemy, Redis-compatible runtime store, Vue 3, Pinia, Vitest, unittest.

## Global Constraints

- AI never exposes arbitrary URLs, SQL, internal formulas, credentials, tokens, raw ledger rows, attachments, or database structure.
- AI remains read-only and permission-aware; scenic analytics require the existing supply-management scenic permission.
- A duplicate client submission may reload the persisted conversation; a conversation-busy conflict must remain an error and preserve the retry UUID.
- Scenic names and IDs come from `list_effective_configs`; configured IDs must remain route-safe and work in backend action validation and frontend action validation.
- A conversation with an active generation lease must not be hard-deleted; owner/admin deletion requests stop first and retention cleanup skips active leases.
- Production must require a shared Redis-backed AI store with `AI_SHARED_STORE_REQUIRED=true`.

---

### Task 1: Enforce Safe Model Output

**Files:**
- Modify: `backend/app/services/ai_orchestrator.py`
- Modify: `backend/app/services/ai_conversations.py`
- Test: `backend/tests/test_ai_orchestrator.py`

**Interfaces:**
- Model text is buffered at sentence boundaries, normalized for policy checks, and only safe segments are emitted and persisted.
- Unsafe or incomplete model output falls back to the existing local unavailable response without leaking the rejected text.

- [ ] Add tests for URLs split across chunks, SQL, internal formulas, and safe text.
- [ ] Implement sentence-buffered output validation for both free-form and data-answer model streams.
- [ ] Run focused orchestrator/conversation tests and commit.

### Task 2: Return Structured Submission Conflicts

**Files:**
- Modify: `backend/app/services/ai_runtime.py`
- Modify: `backend/app/services/ai_conversations.py`
- Modify: `frontend/src/api/aiAssistant.js`
- Modify: `frontend/src/store/aiAssistant.js`
- Test: `backend/tests/test_ai_streaming.py`
- Test: `frontend/src/api/aiAssistant.test.js`
- Test: `frontend/src/store/aiAssistant.test.js`

**Interfaces:**
- Duplicate submission raises HTTP 409 with `detail.code = duplicate_submission`.
- Active conversation generation raises HTTP 409 with `detail.code = conversation_busy`.
- `responseError` exposes `error.code`; only duplicate submission reloads, while busy preserves retry state and rejects.

- [ ] Add backend and frontend regression tests for both codes.
- [ ] Implement structured details and precise store branching.
- [ ] Run focused backend/frontend tests and commit.

### Task 3: Resolve Scenic Intent From Effective Configuration

**Files:**
- Modify: `backend/app/services/ai_orchestrator.py`
- Modify: `frontend/src/utils/safeMarkdown.js`
- Test: `backend/tests/test_ai_orchestrator.py`
- Test: `frontend/src/utils/safeMarkdown.test.js`

**Interfaces:**
- `_allowed_scenics` and local lookup accept a database session/context and use `list_effective_configs(context.db)`.
- Configured scenic IDs/names are canonicalized against that registry before tool execution.
- Backend and frontend accept only the configured route-safe scenic ID format, never arbitrary URLs or path traversal.

- [ ] Add a custom scenic configuration lookup test and route-safe validator tests.
- [ ] Replace static seed resolution with effective configuration registry resolution.
- [ ] Run focused tests and commit.

### Task 4: Coordinate Deletion With Active Generation

**Files:**
- Modify: `backend/app/services/ai_runtime.py`
- Modify: `backend/app/services/ai_conversations.py`
- Modify: `backend/app/jobs/cleanup_ai_conversations.py`
- Test: `backend/tests/test_ai_conversations.py`

**Interfaces:**
- `is_generation_active(conversation_id)` reports the current lease.
- Owner/admin deletion requests stop and waits briefly; if the lease remains, it returns structured `conversation_busy` and does not delete.
- Retention cleanup skips conversations with active leases.

- [ ] Add deletion-race and retention-skip tests.
- [ ] Implement stop/wait/delete coordination with bounded waiting.
- [ ] Run focused and full backend tests and commit.

### Task 5: Validate Operations and Finish

**Files:**
- Modify: `deploy/sd-scm-backend.service`
- Modify: `frontend/e2e/portal-ai.spec.js`
- Modify: `.superpowers/sdd/2026-08-06-ai-security-remediation/progress.md`

- [ ] Require `AI_SHARED_STORE_REQUIRED=true` in the backend unit.
- [ ] Assert the E2E stop endpoint call and intermediate generating state.
- [ ] Run backend, frontend, E2E, and production build gates.
- [ ] Request final whole-branch review, resolve Important findings, push `main`, and deploy production.
