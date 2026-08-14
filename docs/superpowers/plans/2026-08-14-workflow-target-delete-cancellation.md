# Workflow Target Delete Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cancel active workflow state atomically when an eligible contract or approval form is deleted, then rebuild and redeploy a clean release candidate.

**Architecture:** A workflow-engine helper owns cancellation semantics and row locking. Contract and approval-form delete endpoints call it inside their existing transaction before deleting the target, preserving task actions and timeline evidence while removing all actionability.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, pytest 8.3.5, Vue 3.5, Vitest 3.2, Vite 6, MySQL 8, Nginx, systemd, Git, SSH.

## Global Constraints

- Work only in `D:\Investment-management\.worktrees\release-unified-org-production-20260813`; never touch the dirty primary checkout.
- Preserve every workflow task action, actor/signature/governance snapshot, system audit row, and retained timeline.
- Never hard-delete workflow instances, tasks, or task actions during business-record deletion.
- Preserve all existing delete permission, ownership, target-state, approved-record, workflow action, return-target, and CAS constraints.
- Cancellation and target deletion must be one transaction; the helper must not commit.
- Push without force and deploy only an exact commit that passed complete backend/frontend/build validation and independent review.
- Production remains on `7082ed6f991c5695dd54a30af32b90bc4e2a5735` until the replacement candidate passes acceptance.

---

### Task 1: Transactional Workflow Cancellation On Delete

**Files:**
- Modify: `backend/app/services/workflow_engine.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/app/api/v1/endpoints/approval.py`
- Modify: `backend/tests/test_workflow_engine.py`
- Modify: `backend/tests/test_workflow_api.py`

**Interfaces:**
- Produces: `cancel_active_workflow_for_target(db: Session, target_type: WorkflowTargetType, target_id: int) -> WorkflowInstance | None`.
- Consumes: `WorkflowInstanceStatus.ACTIVE/CANCELLED`, `WorkflowTaskStatus.PENDING/ACTIVE/AWAITING_REASSIGNMENT/SKIPPED`, the endpoint-owned SQLAlchemy transaction, and existing contract/approval target-type mapping.

- [ ] **Step 1: Add failing engine cancellation tests**

Add tests that create an active instance containing approved, returned, active, pending, and awaiting-reassignment tasks plus retained actions. Call `cancel_active_workflow_for_target(...)` and assert:

```python
self.assertEqual(instance.status, WorkflowInstanceStatus.CANCELLED)
self.assertIsNotNone(instance.completed_at)
self.assertEqual(active.status, WorkflowTaskStatus.SKIPPED)
self.assertEqual(pending.status, WorkflowTaskStatus.SKIPPED)
self.assertEqual(awaiting.status, WorkflowTaskStatus.SKIPPED)
self.assertEqual(returned.status, WorkflowTaskStatus.RETURNED)
self.assertEqual(approved.status, WorkflowTaskStatus.APPROVED)
self.assertEqual(action.actor_id, original_actor_id)
self.assertEqual(action.signature_snapshot, original_signature)
self.assertEqual(actionable_active_task_counts(self.db, self.admin), {})
```

Also prove no matching instance and an already-cancelled instance are idempotent, and rollback by the caller restores the original statuses.

- [ ] **Step 2: Add failing real API deletion tests**

For both a returned contract and returned business approval form:

1. submit through the existing API;
2. return through the existing workflow action API so the target becomes `rejected`;
3. record the instance, task, and action IDs;
4. delete the target through its normal DELETE API;
5. assert HTTP 200, target absence, instance `cancelled`, no `active`/`pending`/`awaiting_reassignment` tasks, retained returned/approved tasks and actions, timeline access by instance ID, and unchanged admin active counts.

Keep existing approved-target DELETE assertions at HTTP 409.

- [ ] **Step 3: Run focused tests and confirm RED**

Run from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_engine.py tests/test_workflow_api.py -q
```

Expected: new tests fail because deletion leaves an active instance/tasks and the helper does not exist.

- [ ] **Step 4: Implement the cancellation helper**

In `workflow_engine.py`, load the target instance and tasks with row locks. For an active instance, set a single `cancelled_at = datetime.now()`, then:

```python
instance.status = WorkflowInstanceStatus.CANCELLED
instance.completed_at = cancelled_at
for task in tasks:
    if task.status in {
        WorkflowTaskStatus.PENDING,
        WorkflowTaskStatus.ACTIVE,
        WorkflowTaskStatus.AWAITING_REASSIGNMENT,
    }:
        task.status = WorkflowTaskStatus.SKIPPED
        task.completed_at = cancelled_at
        task.version += 1
db.flush()
return instance
```

Return `None` when no instance exists and return a non-active instance unchanged. Do not add actions and do not commit.

- [ ] **Step 5: Integrate both delete endpoints**

After every existing delete guard succeeds and immediately before `db.delete(...)`:

```python
cancel_active_workflow_for_target(
    db,
    WorkflowTargetType.CONTRACT,
    contract.id,
)
```

For approval forms, choose `PAYMENT_APPROVAL` for payment forms and `BUSINESS_APPROVAL` otherwise, then call the same helper. Keep one endpoint commit so cancellation and deletion are atomic.

- [ ] **Step 6: Run focused GREEN tests and commit**

Run:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_engine.py tests/test_workflow_api.py tests/test_company_permissions.py -q
git diff --check
```

Expected: all focused tests pass, including approved-delete and ordinary workflow/CAS regressions.

Commit:

```powershell
git add -- backend/app/services/workflow_engine.py backend/app/api/v1/endpoints/contract.py backend/app/api/v1/endpoints/approval.py backend/tests/test_workflow_engine.py backend/tests/test_workflow_api.py
git commit -m "fix: cancel workflows when deleting targets"
```

---

### Task 2: Validate, Publish, And Redeploy Recovery Candidate

**Files:**
- Verify: all Task 1 files
- Modify after successful production acceptance: `README.md`
- Push: exact tested HEAD to `origin/main`
- Create: versioned local/server artifacts, DB backup, candidate, rollback, and acceptance evidence for the new SHA

**Interfaces:**
- Consumes: the exact Task 1 commit and the release process in `docs/superpowers/plans/2026-08-13-executive-read-superuser-test-access-ui-fixes.md` Task 6.
- Produces: a new GitHub main SHA and matching production `REVISION`/`RELEASE`, with the failed `620125c...` evidence retained.

- [ ] **Step 1: Run complete validation**

Run complete backend pytest, complete frontend Vitest, `npm run build`, `git diff --check`, and `git status --short`. Require all tests/builds to pass and a clean worktree.

- [ ] **Step 2: Perform independent whole-branch review**

Review the diff from `7082ed6f991c5695dd54a30af32b90bc4e2a5735` to HEAD. Require no unresolved Critical or Important findings. Explicitly verify atomic deletion/cancellation, retained actions, zero active orphan counts, and unchanged ordinary authorization/CAS behavior.

- [ ] **Step 3: Push and build exact immutable artifacts**

Fast-forward push tested HEAD to `origin/main`, verify with `ls-remote`, rebuild frontend, create three versioned archives, hash locally/remotely, and retain the prior failed-candidate artifacts.

- [ ] **Step 4: Preflight and deploy with rollback protection**

Repeat production preflight, a fresh DB/application backup, candidate import using authoritative candidate cwd/Python safe-path handling, temporary-DB seed/grant verification, external maintenance verification, live insert-only seed, byte-verified same-filesystem switch, service restart, and 30-second health gate. Preserve `.env`, `.venv`, uploads, business data, prior backups, and both failed/successful evidence trees.

- [ ] **Step 5: Repeat authenticated acceptance with clean deletion**

Repeat every original admin/executive acceptance item. For the disposable returned target, capture baseline admin counts, perform the real admin workflow action and duplicate 409, delete through the normal API, then prove:

```text
target row absent
workflow instance cancelled
no active/pending/awaiting-reassignment task
admin actionable count restored to baseline
task actions and HTTP audit rows retained
timeline still readable by instance ID
```

Verify the live return control/adaptive CSS and clean journal/service state.

- [ ] **Step 6: Finalize markers and README**

Only after acceptance passes, remove maintenance, verify health/services, change the release row to `生产 ✅`, commit `docs: mark access fixes deployed`, prove the final commit changes no backend/frontend/deploy files, push without force, copy README, and set production markers to the final docs SHA. Verify local HEAD, GitHub main, `REVISION`, and `RELEASE` all match.

- [ ] **Step 7: Remove only named temporary helpers**

Delete only the new candidate's uploaded `/tmp` archives and stop only the exact SOCKS process/listener created for the successful push. Retain all versioned backups, candidates, rollbacks, failed-candidate evidence, successful acceptance evidence, and audit rows.
