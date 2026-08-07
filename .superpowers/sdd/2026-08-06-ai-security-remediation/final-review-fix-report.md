# Final review remediation report

Review findings remediated from `ccfab0fb1b3f5b6b10be42c58513e8012b67b78b`.

Commits: `a318e9a`, `e7134bc`.

## Files changed

- `backend/app/api/v1/endpoints/approval.py`
- `backend/app/api/v1/endpoints/approval_stats.py`
- `backend/app/api/v1/endpoints/channel.py`
- `backend/app/api/v1/endpoints/contract.py`
- `backend/app/api/v1/endpoints/customer.py`
- `backend/app/api/v1/endpoints/hotel_ledger.py`
- `backend/app/api/v1/endpoints/invoice.py`
- `backend/app/api/v1/endpoints/knowledge.py`
- `backend/app/api/v1/endpoints/operation.py`
- `backend/app/api/v1/endpoints/scenic.py`
- `backend/app/api/v1/endpoints/ticket_ledger.py`
- `backend/app/core/store.py`
- `backend/app/jobs/cleanup_ai_conversations.py`
- `backend/app/services/ai_conversations.py`
- `backend/app/services/ai_orchestrator.py`
- `backend/tests/test_ai_conversations.py`
- `backend/tests/test_ai_orchestrator.py`
- `backend/tests/test_company_permissions.py`
- `backend/tests/test_store.py`
- `deploy/sd-scm-ai-cleanup.service`
- `frontend/src/api/aiAssistant.js`
- `frontend/src/api/aiAssistant.test.js`
- `frontend/src/store/aiAssistant.js`
- `frontend/src/store/aiAssistant.test.js`

## Security changes

- Supply-chain endpoints now enforce company-resource authorization before record access. Contract and approval workflows resolve effective company role from the database, so a stale token role cannot authorize a user without an active company membership.
- AI input is classified only after the policy rejects credentials, tokens, SQL, raw ledger or attachment content, arbitrary URLs, formulas, database-structure requests, and prompt-injection patterns. Rejected requests do not reach a provider.
- Provider-backed free-form and aggregate answers are buffered and size-limited, then validated before an SSE text event is emitted or any assistant text is persisted. Unsafe or failed provider output falls back to local text. Only explicitly validated `deepseek` events are accepted by conversation persistence.
- A clean SSE EOF without a terminal event is treated as an incomplete stream and marks the optimistic assistant message failed rather than leaving it generating.
- Redis mixed-version active-member tracking preserves legacy Set compatibility while using bounded per-member ZSET expiry. V2 renewals do not extend a pre-existing legacy Set TTL, preventing stale v1 members from being kept alive indefinitely.
- Legacy member scores are materialized before concurrency-capacity rejection, so a full legacy Set cannot prevent its own bounded migration.
- Persisted assistant messages retain `deepseek` engine attribution for validated provider output; local fallback remains explicitly local.
- AI conversation cleanup requires a shared store in the service unit and fails closed when shared-store validation cannot be satisfied.

## Verification

- `python -m unittest tests.test_store tests.test_ai_conversations tests.test_ai_orchestrator -q` from `backend`: passed, 47 tests.
- `python -m unittest discover -s tests -q` from `backend`: passed, 145 tests. Expected test logging includes the fail-closed shared-store cleanup message and the lease-settlement test traceback; the suite exited successfully.
- `npm test` from `frontend`: passed, 15 files and 113 tests.
- `npm run build` from `frontend`: passed. Existing chunk-size and VueUse PURE-comment warnings remain.
- `npm run test:e2e` from `frontend`: passed, 2 Playwright tests.
- `git diff --check`: passed.

## Residual operational notes

- Deployment must provide a reachable shared Redis store for the cleanup unit; it intentionally refuses process-local fallback.
- Provider responses remain availability-dependent, but policy failures and provider errors use the local fallback without persisting unvalidated model text.
