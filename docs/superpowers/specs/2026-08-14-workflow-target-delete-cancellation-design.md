# Workflow Target Delete Cancellation Design

## Context

Production acceptance for candidate `620125cfc0673654802b9eeb02c1657294467c17` deleted a returned disposable contract through `DELETE /api/v1/contracts/{id}`. The business record was removed, but its workflow instance remained `active` and one task remained `active`. Because enabled superusers see and count every active task, admin retained a permanent orphan pending item whose target no longer existed. Production was rolled back to `7082ed6f991c5695dd54a30af32b90bc4e2a5735` before final markers were changed.

## Goal

Deleting an eligible draft or rejected contract/approval form through its normal API must atomically cancel its active workflow so no task remains actionable, while preserving workflow actions, actor snapshots, timeline history, and HTTP audit records.

## Options Considered

1. **Hard-delete workflow rows.** Rejected because cascading from instance to tasks/actions destroys the evidence the acceptance plan requires retaining.
2. **Filter missing targets from inbox/count queries.** Rejected because it hides corrupt active workflow state and leaves direct service paths inconsistent.
3. **Cancel in the target-delete transaction.** Selected because it preserves history, removes actionability at the source, and rolls back together if target deletion fails.

## Design

Add `cancel_active_workflow_for_target(db, target_type, target_id)` to `workflow_engine.py`.

- Lock the matching workflow instance and its tasks.
- If no instance exists, or the instance is not `active`, return without mutation.
- Change the instance to `cancelled` and set `completed_at`.
- Change tasks in `pending`, `active`, or `awaiting_reassignment` to `skipped`, set `completed_at`, and increment `version` so stale task actions cannot win CAS.
- Preserve `approved` and `returned` task statuses, every `wf_task_action`, the instance sequence, actor/signature snapshots, and the legacy projection rows.
- Flush but do not commit; the delete endpoint owns the transaction.

Call the helper immediately before `db.delete(...)` in both contract and approval-form delete endpoints. Permission, ownership, approved-record immutability, and draft/rejected-state guards remain unchanged. Approval-form target type is derived from its real form type.

No database migration or new enum value is required: `WorkflowInstanceStatus.CANCELLED` and `WorkflowTaskStatus.SKIPPED` already exist in the deployed schema.

## Concurrency And Errors

The helper uses row locks and increments affected task versions. Cancellation and target deletion commit together. Any database failure rolls both back; endpoints keep their existing error surface. Calling the helper twice is harmless because only an active instance is mutated.

## Testing

- Engine tests prove cancellation is idempotent, leaves commit to the caller, retains returned/approved history and actions, skips every actionable/not-yet-started task, and removes superuser active counts.
- Real API tests return a contract and an approval form, delete each through the normal endpoint, then prove the target is gone, instance is cancelled, no task is active/actionable, actions/timeline remain, and admin pending counts return to the pre-test value.
- Existing ordinary authorization, approved-delete `409`, workflow CAS, full backend/frontend suites, and production build remain green.

## Release Recovery

The rolled-back production state remains authoritative until a new exact candidate passes focused tests, complete validation, independent review, temporary-database seed verification, atomic deployment, and authenticated acceptance. The prior failed candidate, database backup, rollback tree, and acceptance evidence remain retained for diagnosis.
