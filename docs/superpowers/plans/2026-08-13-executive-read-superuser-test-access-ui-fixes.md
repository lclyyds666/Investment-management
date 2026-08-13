# Executive Read, Superuser Test Access, and UI Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give investment-company executives cross-platform read/export access, make enabled superusers true full-function testers with auditable workflow actions, and repair the system-management return path and organization-tree layout.

**Architecture:** Extend the seeded position-permission catalog for the three investment executive positions while preserving the existing insert-only customization policy. Put the enabled-superuser bypass in the shared backend and frontend authorization adapters, then add an explicit workflow actor-snapshot abstraction so superuser actions use the real actor plus a fixed system-governance identity without fake assignments. Keep the UI changes local to `SystemLayout` and the organization register, and release the exact tested commit through the existing versioned backup/candidate/rollback process.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Pydantic 2, pytest 8.3.5, Vue 3.5, Pinia 2.3, Element Plus 2.9, Vitest 3.2, Vite 6, PowerShell, Git, SSH, MySQL 8, Nginx, systemd.

## Global Constraints

- Work only in `D:\Investment-management\.worktrees\release-unified-org-production-20260813`; do not modify, stage, restore, clean, or otherwise touch the dirty primary checkout at `D:\Investment-management`.
- Keep the `admin` account's legacy role, assignments, username, and profile unchanged; authorization comes only from an enabled `is_superuser=true` account.
- A disabled superuser receives no company, resource, permission, or workflow-action bypass.
- Investment executives are exactly `investment.executive.chairman`, `investment.executive.general_manager`, and `investment.executive.deputy_general_manager`.
- Investment executives receive the three portal-entry permissions, every current `supply.*.view`, every current `supply.*.export`, and `organization.directory.view`.
- Investment executives do not receive `create`, `update`, `delete`, `submit`, `review`, `approve`, `return`, or `configure` actions; real mutation endpoints must continue returning HTTP 403.
- Do not add current workflow nodes or workflow qualifications for the three investment executive positions.
- Enabled superusers may use every backend permission, frontend company/resource/permission gate, and every currently active workflow task, including submit/resubmit, approve, and return actions.
- Enabled superusers still obey target state, workflow action validity, return-target validity, optimistic CAS conflict, and completed/cancelled/non-active task constraints.
- Every superuser workflow action records the real `actor_id`, `actor_name`, and signature plus `system.governance` / `系统治理` / `system.superuser` / `超级管理员` as its governance snapshot.
- Do not create a fake organization, position, assignment, governance scope, or external-assignment row for superusers.
- Preserve the insert-only behavior of `seed_authorization_catalog`; do not delete or overwrite administrator-customized grants.
- Production release must preserve `/opt/sd-scm/backend/.env`, `/opt/sd-scm/backend/.venv`, `/opt/sd-scm/backend/uploads`, business data, and the active release until all preflight gates pass.
- Push without force and deploy only the exact GitHub `main` commit that passed the complete backend suite, complete frontend suite, and production frontend build.

---

## File Map

- `backend/app/services/organization_catalog.py`: defines the executive read-only grant template and seeds only missing position-permission links.
- `backend/app/services/assignment_permissions.py`: owns enabled-superuser permission bypass while keeping `has_position` truthful.
- `backend/app/services/permissions.py`: projects all registered supply resources for enabled superusers.
- `backend/app/services/portal.py`: exposes all three applications and a full registered permission/resource snapshot to enabled superusers.
- `backend/app/api/v1/endpoints/contract.py`: exposes all contracts to enabled superusers and lets them resubmit any returned active handler task while preserving normal record ownership for edits/deletes/uploads.
- `backend/app/api/v1/endpoints/approval.py`: lets enabled superusers resubmit any returned active approval-form handler task while preserving normal record ownership for edits/deletes/uploads.
- `backend/app/api/v1/endpoints/approval_stats.py`: includes every active contract/form task in the enabled-superuser navigation counts.
- `backend/app/services/workflow_engine.py`: owns active-task visibility, superuser task actionability, workflow submission/resubmission, and immutable actor/governance snapshots.
- `backend/tests/test_assignment_permissions.py`: locks catalog topology, executive read-only boundaries, and superuser adapter behavior.
- `backend/tests/test_company_permissions.py`: proves executive read/download access and mutation denial through real API dependencies.
- `backend/tests/test_portal_api.py`: locks three-platform access and permission snapshots for executives and superusers.
- `backend/tests/test_workflow_engine.py`: locks active-task visibility, submission/action behavior, snapshots, and normal-user/CAS invariants.
- `backend/tests/test_workflow_api.py`: locks superuser approve/return HTTP behavior, inbox/count projections, conflict actor details, and audit projections.
- `backend/tests/test_company_permissions.py`: also proves enabled-superuser all-contract visibility and representative write API access on admin-owned disposable records.
- `frontend/src/store/portal.js`: owns frontend company/resource/permission superuser bypass while leaving positions assignment-backed.
- `frontend/src/store/portal.test.js`: locks the store-level bypass and truthful positions.
- `frontend/src/utils/businessAuthorization.js`: exposes superuser business-action and active-workflow predicates.
- `frontend/src/utils/businessAuthorization.test.js`: locks the superuser action behavior and non-active task denial.
- `frontend/src/layout/SystemLayout.vue`: adds the always-visible “返回工作平台” action to `/`.
- `frontend/src/layout/SystemLayout.test.js`: locks the route target and existing seven system menu entries.
- `frontend/src/views/system/organization.vue`: makes the register column and tree node rows adaptive.
- `frontend/src/views/system/organization.test.js`: statically locks the scoped Element Plus tree layout rules.
- `README.md`: updates the capability description and 2026-08-13 iteration status.

---

### Task 1: Executive Read Grants and Shared Authorization Adapters

**Files:**
- Modify: `backend/tests/test_assignment_permissions.py`
- Modify: `backend/tests/test_company_permissions.py`
- Modify: `backend/tests/test_portal_api.py`
- Modify: `backend/app/services/organization_catalog.py`
- Modify: `backend/app/services/assignment_permissions.py`
- Modify: `backend/app/services/permissions.py`
- Modify: `backend/app/services/portal.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`

**Interfaces:**
- Consumes: `PERMISSION_CODES`, `SUPPLY_VIEW_PERMISSIONS`, `SUPPLY_EXPORT_PERMISSIONS`, `PermissionContext`, `RESOURCE_VIEW_PERMISSIONS`, and the existing insert-only `seed_authorization_catalog(db: Session) -> None` behavior.
- Produces: `INVESTMENT_EXECUTIVE_POSITION_CODES: tuple[str, ...]`, `INVESTMENT_EXECUTIVE_READ_PERMISSIONS: frozenset[str]`, `has_permission(...) -> bool` with an enabled-superuser bypass, all supply resources from `allowed_resources(...)`, all three accessible `PortalApplicationOut` rows, and a complete registered `PortalPermissionSnapshot` for enabled superusers.

- [ ] **Step 1: Write failing catalog and adapter tests**

In `AuthorizationCatalogTest` add a topology test that derives its expectation from the catalog constants, so future `supply.*.view` and `supply.*.export` additions are automatically required for all three executives:

```python
def test_investment_executives_receive_only_cross_platform_read_permissions(self):
    executive_positions = {
        "investment.executive.chairman",
        "investment.executive.general_manager",
        "investment.executive.deputy_general_manager",
    }
    expected_permissions = {
        "investment.portal.enter",
        "supply.portal.enter",
        "fund.portal.enter",
        "organization.directory.view",
        *{
            item["code"]
            for item in PERMISSION_CATALOG
            if item["code"].startswith("supply.")
            and item["code"].endswith((".view", ".export"))
        },
    }
    forbidden_actions = {
        "create", "update", "delete", "submit", "review",
        "approve", "return", "configure",
    }

    for position_code in executive_positions:
        with self.subTest(position_code=position_code):
            grants = [
                item for item in POSITION_GRANTS
                if item["position_code"] == position_code
            ]
            self.assertEqual(
                {item["permission_code"] for item in grants},
                expected_permissions,
            )
            self.assertFalse({
                item["permission_code"].rsplit(".", 1)[-1]
                for item in grants
            } & forbidden_actions)
```

Replace `test_superuser_with_business_assignment_is_denied_by_authorization_adapters` with tests that keep positions real but allow every permission only while the account is enabled:

```python
def test_enabled_superuser_bypasses_permission_but_not_position_checks(self):
    self.assertFalse(has_position(self.db, self.admin.id, "supply.business_handler"))
    for permission_code in (
        "supply.contract.submit",
        "supply.approval.approve",
        "supply.channel.configure",
        "future.permission.not-yet-seeded",
    ):
        with self.subTest(permission_code=permission_code):
            self.assertTrue(has_permission(
                self.db,
                self.admin,
                permission_code,
                PermissionContext(company_code="supplymanagement"),
            ))

def test_disabled_superuser_has_no_permission_bypass(self):
    self.admin.is_active = False
    self.db.commit()
    self.assertFalse(has_permission(
        self.db,
        self.admin,
        "supply.contract.view",
        PermissionContext(company_code="supplymanagement"),
    ))
```

- [ ] **Step 2: Write failing portal tests for all executives and the superuser**

Replace the investment-hierarchy denial test with a table-driven test covering all three executive positions:

```python
def test_each_investment_executive_can_enter_all_three_applications(self):
    for index, position_code in enumerate((
        "investment.executive.chairman",
        "investment.executive.general_manager",
        "investment.executive.deputy_general_manager",
    )):
        with self.subTest(position_code=position_code):
            user = self.add_user(f"investment-executive-{index}")
            self.add_assignment(user, "investment", position_code)
            apps = applications_for_user(self.db, user)
            self.assertEqual([item.accessible for item in apps], [True, True, True])
            self.assertEqual([item.denial_reason for item in apps], [None, None, None])
```

Replace `test_superuser_with_platform_assignment_has_no_business_applications` and the matching denial-reason assertion with:

```python
def test_enabled_superuser_can_enter_every_application_without_assignments(self):
    apps = applications_for_user(self.db, self.admin)
    self.assertEqual([item.accessible for item in apps], [True, True, True])
    self.assertEqual([item.denial_reason for item in apps], [None, None, None])
```

In `PortalPermissionSnapshotTest`, add one user for each executive position and assert the exact read-only permission boundary. Replace the superuser empty-snapshot test with:

```python
def test_superuser_snapshot_projects_all_registered_permissions_and_resources(self):
    snapshot = permission_snapshot_for_user(self.db, self.admin)

    self.assertTrue(snapshot.is_superuser)
    self.assertEqual(snapshot.assignments, [])
    self.assertEqual(
        {item.code for item in snapshot.permissions},
        {item["code"] for item in PERMISSION_CATALOG},
    )
    self.assertEqual(
        set(snapshot.resources),
        {resource.value for resource in RESOURCE_VIEW_PERMISSIONS},
    )
```

- [ ] **Step 3: Write a failing real-API read/write boundary test**

In `ResourceSpecificEndpointTest`, create a real executive user and assignment, then exercise the dependency guards rather than only inspecting the seed catalog:

```python
def test_investment_executive_can_read_and_download_but_cannot_mutate(self):
    self._add_current_user()
    organization_id = self.db.scalar(
        select(Organization.id).where(Organization.code == "investment")
    )
    position_id = self.db.scalar(
        select(Position.id).where(
            Position.code == "investment.executive.general_manager"
        )
    )
    self.db.add(UserAssignment(
        user_id=self.current_user.id,
        organization_id=organization_id,
        position_id=position_id,
        valid_from=date(2026, 1, 1),
        status=AssignmentStatus.ACTIVE,
    ))
    self.db.commit()

    self.assertEqual(self.client.get("/api/v1/contracts").status_code, 200)
    self.assertNotEqual(
        self.client.get("/api/v1/contracts/999/attachment").status_code,
        403,
    )
    self.assertEqual(
        self.client.post(
            "/api/v1/contracts",
            json={"contract_no": "EXEC-WRITE", "title": "Denied"},
        ).status_code,
        403,
    )
    self.assertEqual(
        self.client.post(
            "/api/v1/channels",
            json={"name": "Denied"},
        ).status_code,
        403,
    )
```

- [ ] **Step 4: Run the focused backend tests and verify they fail**

Run from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_assignment_permissions.py tests/test_portal_api.py tests/test_company_permissions.py -q
```

Expected: failures show executive supply/fund access is missing, executive mutation boundaries are not yet backed by the new grants, and enabled superusers still return false/empty from shared adapters and portal projections.

- [ ] **Step 5: Implement the executive grant template**

In `organization_catalog.py`, define the executive positions and exact read permission set immediately after the supply view/export constants:

```python
INVESTMENT_EXECUTIVE_POSITION_CODES = (
    "investment.executive.chairman",
    "investment.executive.general_manager",
    "investment.executive.deputy_general_manager",
)

INVESTMENT_EXECUTIVE_READ_PERMISSIONS = frozenset({
    "investment.portal.enter",
    "supply.portal.enter",
    "fund.portal.enter",
    "organization.directory.view",
}) | SUPPLY_VIEW_PERMISSIONS | SUPPLY_EXPORT_PERMISSIONS
```

Replace the three existing one-off investment-portal entries with one executive generator. It emits the three portal-entry grants using `platform` and the matching platform code, then emits every supply view/export grant using `company` with `scope_ref="supplymanagement"`. Do not emit `organization.directory.view` from the new generator because the existing non-external-position directory generator already supplies that exact company-scoped link; this avoids duplicate catalog entries. Keep the existing seed loop unchanged so only missing database links are inserted. The resulting `POSITION_GRANTS` must contain exactly one item per `(executive position, permission code)` and no action outside `INVESTMENT_EXECUTIVE_READ_PERMISSIONS`.

Extend the topology test to assert scope as well as permission names:

```python
for grant in grants:
    code = grant["permission_code"]
    if code == "investment.portal.enter":
        self.assertEqual((grant["data_scope"], grant["scope_ref"]), ("platform", "investment"))
    elif code == "supply.portal.enter":
        self.assertEqual((grant["data_scope"], grant["scope_ref"]), ("platform", "supplymanagement"))
    elif code == "fund.portal.enter":
        self.assertEqual((grant["data_scope"], grant["scope_ref"]), ("platform", "fundmanagement"))
    else:
        self.assertEqual((grant["data_scope"], grant["scope_ref"]), ("company", "supplymanagement"))
```

- [ ] **Step 6: Implement enabled-superuser adapters and portal projection**

Change `has_permission` to short-circuit only enabled superusers:

```python
if user.is_superuser:
    return bool(user.is_active)
```

Keep `has_position` unchanged so it never invents an assignment for a superuser.

In `allowed_resources`, return all registered supply resources for an enabled superuser and preserve the existing company check:

```python
if company != CompanyCode.SUPPLY_MANAGEMENT:
    return frozenset()
if user.is_superuser and user.is_active:
    return frozenset(RESOURCE_VIEW_PERMISSIONS)
```

In `applications_for_user`, use:

```python
enabled_superuser = bool(user.is_superuser and user.is_active)
accessible = enabled_superuser or enter_permission in platform_permissions
```

In `permission_snapshot_for_user`, query all active registered `Permission` rows for an enabled superuser, project each as a `PermissionGrantOut(code=code, data_scope=DataScope.PLATFORM.value, scope_ref="")`, return all values from `RESOURCE_VIEW_PERMISSIONS`, keep assignments empty, and set `company_roles={}`. Return an empty non-authorizing snapshot for an inactive superuser rather than falling through to assignment-derived grants.

In `contract.py`, make `_visible_contract_ids` return `None` for an enabled superuser before it inspects assignment-derived grants. This is required because the contract list/detail/download visibility helper currently bypasses `has_permission` and would otherwise reject admin despite the shared permission shortcut.

- [ ] **Step 7: Run focused authorization tests**

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_assignment_permissions.py tests/test_portal_api.py tests/test_company_permissions.py -q
```

Expected: all three files pass, including real API 200/non-403 read/download behavior and HTTP 403 mutation behavior for an investment executive.

- [ ] **Step 8: Commit the authorization slice**

```powershell
git add -- backend/app/services/organization_catalog.py backend/app/services/assignment_permissions.py backend/app/services/permissions.py backend/app/services/portal.py backend/app/api/v1/endpoints/contract.py backend/tests/test_assignment_permissions.py backend/tests/test_company_permissions.py backend/tests/test_portal_api.py
git commit -m "feat: add executive read and superuser access"
```

---

### Task 2: Auditable Superuser Workflow Testing

**Files:**
- Modify: `backend/tests/test_workflow_engine.py`
- Modify: `backend/tests/test_workflow_api.py`
- Modify: `backend/app/services/workflow_engine.py`
- Modify: `backend/app/api/v1/endpoints/contract.py`
- Modify: `backend/app/api/v1/endpoints/approval.py`
- Modify: `backend/app/api/v1/endpoints/approval_stats.py`
- Modify: `backend/tests/test_company_permissions.py`

**Interfaces:**
- Consumes: active `User`, `WorkflowTask`, optional real `UserAssignment`, existing workflow state/CAS transitions, `start_workflow(...)`, `complete_task(...)`, `my_active_tasks(...)`, and `actionable_active_task_counts(...)`.
- Produces: immutable `WorkflowActorSnapshot`, `_workflow_actor_snapshot(actor: User, assignment: UserAssignment | None) -> WorkflowActorSnapshot`, enabled-superuser start/resubmit/approve/return behavior, all-active-task inbox/count results, and fixed system-governance snapshots without persisted fake assignments.

- [ ] **Step 1: Replace opposite engine assertions with failing superuser behavior tests**

Replace `test_superuser_cannot_act_without_business_assignment` with:

```python
def test_enabled_superuser_can_act_on_designated_and_shared_active_tasks(self):
    self.shared_task.status = WorkflowTaskStatus.ACTIVE
    self.db.commit()

    self.assertTrue(task_is_actionable_by(self.db, self.designated_task, self.admin))
    self.assertTrue(task_is_actionable_by(self.db, self.shared_task, self.admin))

    self.admin.is_active = False
    self.db.commit()
    self.assertFalse(task_is_actionable_by(self.db, self.designated_task, self.admin))
```

Update the inbox test to assert the superuser sees both active tasks ordered by the existing query order:

```python
self.assertEqual(
    {task.id for task in my_active_tasks(self.db, self.admin)},
    {self.designated_task.id, self.shared_task.id},
)
```

Add an action/snapshot test:

```python
def test_superuser_approval_records_real_actor_and_system_governance_snapshot(self):
    complete_task(
        self.db,
        self.designated_task.id,
        self.admin,
        WorkflowAction.APPROVE,
        "admin test approval",
    )
    action = self.db.scalar(select(WorkflowTaskAction).where(
        WorkflowTaskAction.task_id == self.designated_task.id,
    ))

    self.assertEqual(action.actor_id, self.admin.id)
    self.assertEqual(action.actor_name, self.admin.full_name)
    self.assertEqual(action.organization_code, "system.governance")
    self.assertEqual(action.organization_name, "系统治理")
    self.assertEqual(action.position_code, "system.superuser")
    self.assertEqual(action.position_name, "超级管理员")
    self.assertEqual(action.signature_snapshot, self.admin.signature)
    self.assertEqual(
        self.db.scalar(select(UserAssignment).where(
            UserAssignment.user_id == self.admin.id,
        )),
        None,
    )
```

- [ ] **Step 2: Add failing submit/resubmit and count coverage**

Add an engine test that creates a draft owned by the unassigned enabled superuser, selects the normal valid designated users, and calls `start_workflow`. Assert that the sequence-zero action carries the fixed superuser snapshot and the first approval task becomes active. Add a returned sequence-zero task belonging to a workflow originally submitted by another user and call `complete_task(..., WorkflowAction.SUBMIT, ...)` as the superuser; this proves arbitrary active handler-task resubmission is not accidentally left assignment-bound.

Add an `actionable_active_task_counts` assertion with one active contract task and one active approval-form task. The enabled superuser must receive both grouped counts; after `is_active=False`, it must receive `{}`.

- [ ] **Step 3: Replace the opposite API test with failing approve/conflict/snapshot assertions**

Replace `test_superuser_cannot_approve_and_second_action_returns_actor_snapshot` with:

```python
def test_superuser_can_approve_and_second_action_returns_admin_snapshot(self):
    task = self.active_task()
    self.current_user = self.admin
    approved = self.client.post(
        f"/api/v1/workflows/tasks/{task.id}/approve",
        json={"comment": "admin test"},
    )
    self.assertEqual(approved.status_code, 200, approved.text)

    self.current_user = self.other_leader
    conflict = self.client.post(
        f"/api/v1/workflows/tasks/{task.id}/approve",
        json={"comment": "late"},
    )
    self.assertEqual(conflict.status_code, 409)
    self.assertEqual(conflict.json()["detail"]["actor"], self.admin.full_name)

    action = self.db.scalar(select(WorkflowTaskAction).where(
        WorkflowTaskAction.task_id == task.id,
    ))
    self.assertEqual(action.actor_id, self.admin.id)
    self.assertEqual(action.organization_code, "system.governance")
    self.assertEqual(action.position_code, "system.superuser")
```

Extend the pending-count API test so an enabled superuser sees all ordinary active tasks plus the existing `reassignment` count, rather than business total zero. Add one API reject case on a later active node with `allow_reject=True` and assert the return projection in `Approval` or `ApprovalFormAction` also carries `system.governance` and `system.superuser`.

- [ ] **Step 4: Run focused workflow tests and verify they fail**

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_engine.py tests/test_workflow_api.py -q
```

Expected: failures show the superuser cannot yet see/action tasks, cannot submit its own draft without a handler assignment, cannot resubmit another user's active handler task, receives zero actionable counts, and cannot produce the fixed audit snapshot.

- [ ] **Step 5: Add the workflow actor snapshot abstraction**

Near the existing workflow dataclasses, add:

```python
@dataclass(frozen=True)
class WorkflowActorSnapshot:
    organization_code: str
    organization_name: str
    position_code: str
    position_name: str


def _workflow_actor_snapshot(
    actor: User,
    assignment: UserAssignment | None,
) -> WorkflowActorSnapshot:
    if actor.is_active and actor.is_superuser:
        return WorkflowActorSnapshot(
            organization_code="system.governance",
            organization_name="系统治理",
            position_code="system.superuser",
            position_name="超级管理员",
        )
    if assignment is None:
        raise WorkflowValidationError(
            "workflow_task_not_actionable",
            "The actor is not authorized for this task.",
        )
    return WorkflowActorSnapshot(
        organization_code=assignment.organization.code,
        organization_name=assignment.organization.name,
        position_code=assignment.position.code,
        position_name=assignment.position.name,
    )
```

Use this helper for both sequence-zero submit actions and `_complete_task` actions. Continue writing `actor.id`, `actor.full_name`, and `actor.signature` directly so audit identity remains the real account.

- [ ] **Step 6: Implement active-task visibility and count shortcuts**

At the start of `task_is_actionable_by`, after rejecting inactive users, return `task.status == WorkflowTaskStatus.ACTIVE` for enabled superusers. Do not call `_effective_task_assignment` in that branch.

In `my_active_tasks`, add an enabled-superuser query selecting every `WorkflowTask.status == ACTIVE`, preserving the optional `target_type`, eager loads, and existing `(submitted_at, sequence, id)` order.

In `actionable_active_task_counts`, after `refresh_invalid_designated_tasks` add an enabled-superuser grouped query over all remaining active tasks. Return the same `dict[WorkflowTargetType, int]` shape. Disabled superusers continue to return `{}`.

- [ ] **Step 7: Implement submit, resubmit, approve, and return bypasses**

Load the submitter `User` inside `_start_workflow`. Change `_validate_start_assignments` to accept that `User` and return `tuple[UserAssignment | None, dict[str, UserAssignment]]`. For an enabled superuser, skip only the submit-node assignment check; continue validating target ownership, every designated node/user/assignment, target draft state, workflow publication, and designation completeness. Use the real submitter plus `_workflow_actor_snapshot` when `submit_assignment` is `None`.

In `_complete_task`, calculate:

```python
enabled_superuser = bool(actor and actor.is_active and actor.is_superuser)
```

Keep the existing task existence, active status, allowed action, return permission, CAS, return target, next-node activation, and target status checks. Allow a missing `_resubmission_assignment` or `_effective_task_assignment` only when `enabled_superuser` is true, then build the action fields from `_workflow_actor_snapshot(actor, assignment)`.

- [ ] **Step 8: Implement API resubmission and pending-count projections**

In `test_workflow_api.py`, create a contract and approval form whose workflow was originally submitted by a normal handler, return each to its sequence-zero handler task, switch `current_user` to the enabled superuser, and call the existing contract/form `/submit` endpoint. Assert HTTP 200, the same workflow instance advances, and the new submit projection carries the real admin actor plus `system.governance` / `system.superuser`.

Refactor `submit_contract` and `submit_form` so the initial submission path keeps the existing `created_by == current_user.id` requirement. In the existing-workflow resubmission path, allow an enabled superuser past both `created_by` and `instance.submitted_by` checks, but still require an active `auto_complete_on_submit` task. Do not relax update, delete, attachment-owner, initial-submit-owner, approved-record, state, reason, or CAS checks.

In `approval_stats.py`, remove the superuser branches that force `grant_codes` and `counts` to empty. For an enabled superuser, call `actionable_active_task_counts`, treat both `_VIEW_PERMISSIONS` as granted, calculate contract/business/total from the result, and append the existing `reassignment` count. Keep ordinary permission-scope behavior unchanged.

In `ResourceSpecificEndpointTest`, add a real enabled superuser with no assignments and prove it can list all contracts and create/update/delete representative disposable records it owns through the normal API guards. Keep the existing approved-record delete test at HTTP 409 and ordinary user ownership/permission tests at HTTP 403.

- [ ] **Step 9: Run focused workflow and superuser operation tests**

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest tests/test_workflow_engine.py tests/test_workflow_api.py tests/test_company_permissions.py -q
```

Expected: all focused tests pass; ordinary ownership/designated/shared restrictions and existing CAS conflict tests remain green while enabled-superuser own-record operations and arbitrary-active-task submit/resubmit/approve/return actions succeed with the fixed governance snapshot.

- [ ] **Step 10: Commit the workflow and operation slice**

```powershell
git add -- backend/app/services/workflow_engine.py backend/app/api/v1/endpoints/contract.py backend/app/api/v1/endpoints/approval.py backend/app/api/v1/endpoints/approval_stats.py backend/tests/test_workflow_engine.py backend/tests/test_workflow_api.py backend/tests/test_company_permissions.py
git commit -m "feat: enable auditable superuser workflow operations"
```

---

### Task 3: Frontend Superuser Authorization

**Files:**
- Modify: `frontend/src/store/portal.test.js`
- Modify: `frontend/src/utils/businessAuthorization.test.js`
- Modify: `frontend/src/store/portal.js`
- Modify: `frontend/src/utils/businessAuthorization.js`

**Interfaces:**
- Consumes: `permissions.value.is_superuser`, portal application snapshots, resource/permission arrays, assignment snapshots, and workflow rows with `status` and `current_role`.
- Produces: `hasCompany(companyCode)`, `hasResource(resourceCode)`, and `hasPermission(permissionCode)` enabled-superuser bypasses; assignment-backed `hasPosition(positionCode)`; and `canActOnWorkflow(...)` that allows enabled superusers only for pending rows.

- [ ] **Step 1: Replace opposite frontend unit tests**

Replace `does not treat superuser as a business permission bypass` in `portal.test.js` with:

```javascript
it('treats superuser as company resource and permission bypass without fake positions', async () => {
  portalApi.getPortalApplications.mockResolvedValue([])
  portalApi.getMyPortalPermissions.mockResolvedValue({
    is_superuser: true,
    assignments: [],
    permissions: [],
    resources: []
  })

  const store = usePortalStore()
  await store.loadPortalContext()

  expect(store.hasPermission('supply.contract.approve')).toBe(true)
  expect(store.hasResource('supply.scenic.analytics')).toBe(true)
  expect(store.hasCompany('fundmanagement')).toBe(true)
  expect(store.hasPosition('supply.business_handler')).toBe(false)
})
```

Replace the superuser denial test in `businessAuthorization.test.js` with:

```javascript
it('grants all business permissions and pending workflow actions to a superuser', () => {
  const portalStore = portalSnapshot({ isSuperuser: true })

  expect(canUsePermission(portalStore, 'supply.customer.create')).toBe(true)
  expect(canActOnWorkflow(portalStore, {
    status: 'pending',
    current_role: 'scm_director'
  }, 'supply.approval.approve')).toBe(true)
  expect(canActOnWorkflow(portalStore, {
    status: 'approved',
    current_role: 'scm_director'
  }, 'supply.approval.approve')).toBe(false)
})
```

- [ ] **Step 2: Run focused frontend tests and verify they fail**

Run from `frontend`:

```powershell
npm test -- --run src/store/portal.test.js src/utils/businessAuthorization.test.js
```

Expected: superuser company/resource/permission and workflow assertions fail while truthful `hasPosition` still passes.

- [ ] **Step 3: Implement the store and workflow predicates**

In `portal.js`, change only these helpers:

```javascript
function hasCompany(companyCode) {
  return isSuperuser.value
    || applications.value.some(item => item.code === companyCode && item.accessible)
}

function hasResource(resourceCode) {
  return isSuperuser.value || (permissions.value.resources || []).includes(resourceCode)
}

function hasPermission(permissionCode) {
  return isSuperuser.value
    || (permissions.value.permissions || []).some(item => item.code === permissionCode)
}
```

Do not change `hasPosition`.

In `businessAuthorization.js`, use:

```javascript
export function canUsePermission(portalStore, permissionCode) {
  return portalStore.isSuperuser || portalStore.hasPermission(permissionCode)
}

export function canActOnWorkflow(portalStore, row, permissionCode) {
  if (row?.status !== 'pending') return false
  if (portalStore.isSuperuser) return true
  const positionCode = WORKFLOW_ROLE_POSITIONS[row?.current_role]
  return Boolean(positionCode)
    && portalStore.hasPermission(permissionCode)
    && portalStore.hasPosition(positionCode)
}
```

- [ ] **Step 4: Run focused frontend tests**

```powershell
npm test -- --run src/store/portal.test.js src/utils/businessAuthorization.test.js
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the frontend authorization slice**

```powershell
git add -- frontend/src/store/portal.js frontend/src/store/portal.test.js frontend/src/utils/businessAuthorization.js frontend/src/utils/businessAuthorization.test.js
git commit -m "feat: expose superuser business controls"
```

---

### Task 4: System Return Entry and Adaptive Organization Tree

**Files:**
- Modify: `frontend/src/layout/SystemLayout.test.js`
- Modify: `frontend/src/views/system/organization.test.js`
- Modify: `frontend/src/layout/SystemLayout.vue`
- Modify: `frontend/src/views/system/organization.vue`

**Interfaces:**
- Consumes: the existing `/system` layout, `useRouter()`, all seven current system child routes, Element Plus tree DOM classes, and the existing 760px stacked-layout breakpoint.
- Produces: `returnToWorkspace() -> Promise | void` routing to `/`, an always-visible “返回工作平台” button, and adaptive multi-line organization tree nodes with a responsive register column.

- [ ] **Step 1: Write the failing return-entry test**

Hoist a router `push` spy in `SystemLayout.test.js`, include it in the `useRouter` mock, add an `ElButton` stub that emits click, and add:

```javascript
it('returns from every system page to the work platform', async () => {
  wrapper = shallowMount(SystemLayout, { global: { stubs } })

  const button = wrapper.get('[data-testid="return-workspace"]')
  expect(button.text()).toContain('返回工作平台')
  await button.trigger('click')
  expect(routerPush).toHaveBeenCalledWith('/')
})
```

Keep the existing assertion for all seven system menu routes unchanged.

- [ ] **Step 2: Write the failing scoped-style regression test**

In `organization.test.js`, import the source with Node's URL-safe file API:

```javascript
import { readFileSync } from 'node:fs'

const organizationSource = readFileSync(
  new URL('./organization.vue', import.meta.url),
  'utf8'
)
```

Add:

```javascript
it('uses adaptive multi-line tree node sizing', () => {
  expect(organizationSource).toContain(':deep(.el-tree-node__content)')
  expect(organizationSource).toMatch(/height:\s*auto/)
  expect(organizationSource).toMatch(/min-height:\s*48px/)
  expect(organizationSource).toMatch(/overflow-wrap:\s*anywhere/)
  expect(organizationSource).toMatch(/grid-template-columns:\s*clamp\(/)
  expect(organizationSource).toMatch(/padding-block:\s*6px/)
})
```

- [ ] **Step 3: Run focused layout tests and verify they fail**

```powershell
npm test -- --run src/layout/SystemLayout.test.js src/views/system/organization.test.js
```

Expected: the return button is absent and the organization source lacks adaptive Element Plus tree rules.

- [ ] **Step 4: Add the return-to-workspace control**

In `SystemLayout.vue`, place a toolbar immediately below `GlobalHeader`, outside the collapsible sidebar:

```vue
<div class="system-toolbar">
  <el-button
    data-testid="return-workspace"
    plain
    @click="returnToWorkspace"
  >
    返回工作平台
  </el-button>
</div>
```

Add:

```javascript
function returnToWorkspace() {
  return router.push('/')
}
```

Style `.system-toolbar` as a non-shrinking flex row aligned to the right with 12px vertical and 20px horizontal padding, background `var(--el-bg-color)`, and a bottom border `1px solid var(--surface-border)`. At `max-width:760px`, keep the button visible and use 12px horizontal padding.

- [ ] **Step 5: Make organization tree rows and columns adaptive**

Replace the compressed organization stylesheet with readable scoped rules containing these exact invariants:

```css
.organization-register {
  display: grid;
  grid-template-columns: clamp(280px, 32vw, 420px) minmax(0, 1fr);
  gap: 18px;
  padding: 20px;
  min-height: 100%;
  background: var(--app-bg);
}

:deep(.el-tree-node__content) {
  height: auto;
  min-height: 48px;
  align-items: flex-start;
  padding-block: 6px;
}

:deep(.el-tree-node__expand-icon) {
  margin-top: 4px;
}

.tree-node {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  width: 100%;
  line-height: 1.25;
}

.tree-node b,
.tree-node small {
  overflow-wrap: anywhere;
  white-space: normal;
}
```

Give the tree a top/bottom margin that separates it from both “组织治理名录” and “新建组织”. Preserve `@media (max-width:760px) { .organization-register { grid-template-columns: 1fr; } }`.

- [ ] **Step 6: Run focused layout tests**

```powershell
npm test -- --run src/layout/SystemLayout.test.js src/views/system/organization.test.js
```

Expected: the return navigation, seven menus, organization hierarchy behavior, form behavior, and adaptive CSS assertions all pass.

- [ ] **Step 7: Commit the UI repair slice**

```powershell
git add -- frontend/src/layout/SystemLayout.vue frontend/src/layout/SystemLayout.test.js frontend/src/views/system/organization.vue frontend/src/views/system/organization.test.js
git commit -m "fix: improve system navigation and organization tree"
```

---

### Task 5: Documentation, Full Regression, and Review Gate

**Files:**
- Modify: `README.md`
- Verify: all files committed by Tasks 1–4

**Interfaces:**
- Consumes: completed backend/frontend slices and the approved design in `docs/superpowers/specs/2026-08-13-executive-read-superuser-test-access-ui-fixes-design.md`.
- Produces: current documentation, a clean fully tested release candidate, and a review gate with no unresolved Important findings.

- [ ] **Step 1: Update README capability boundaries before deployment**

Change the user/permission and system-management descriptions so they state:

- investment chairman, general manager, and deputy general manager have cross-platform read/download/export access only;
- enabled superusers are full-function testers and their workflow actions retain real-actor plus fixed governance snapshots;
- system management has a return-to-work-platform entry and adaptive organization-tree rows.

Replace the obsolete sentence that says the superuser “does not obtain business approval permission” with the new test-account boundary. Append a second `2026-08-13` iteration row titled “高管跨平台只读 + 超管全功能测试 + 系统界面修复” and mark it `待部署 🟡`.

- [ ] **Step 2: Run the complete backend suite**

Run from `backend`:

```powershell
& 'D:\Investment-management\.release-artifacts\43f417bcd9076abc8e3637d974e9549c477fd3bf\verify-venv\Scripts\python.exe' -m pytest -q
```

Expected: every backend test passes; the baseline was 344 tests, and the final count is higher because this plan adds authorization and workflow cases.

- [ ] **Step 3: Run the complete frontend suite and production build**

Run from `frontend`:

```powershell
npm test -- --run
npm run build
```

Expected: every frontend test passes; the baseline was 203 tests, the final count is higher, and Vite emits `frontend/dist/index.html` plus hashed assets with exit code zero.

- [ ] **Step 4: Run repository integrity checks**

Run from the worktree root:

```powershell
git diff --check
git status --short
git diff --stat 7082ed6f991c5695dd54a30af32b90bc4e2a5735..HEAD
```

Expected: no whitespace errors; only intentional task files and the approved spec/plan are present; no primary-checkout files, secrets, build artifacts, uploads, database files, or release archives are tracked.

- [ ] **Step 5: Review the implementation against the approved design**

Use the `requesting-code-review` skill. The review request must explicitly verify:

1. the three executive positions receive only the exact read/export template;
2. enabled and disabled superuser paths differ correctly;
3. no fake superuser assignment or organization is persisted;
4. workflow submit/resubmit/approve/return actions retain state/CAS constraints and fixed snapshots;
5. ordinary workflow authorization remains unchanged;
6. the return button and adaptive tree work at desktop and 760px layouts;
7. tests prove real API 403 behavior rather than only checking frontend visibility.

Resolve every Critical or Important finding, rerun the focused tests for changed files, then rerun Steps 2–4. Do not proceed with an unresolved Important finding.

- [ ] **Step 6: Commit documentation and review corrections**

```powershell
git add -- README.md
git commit -m "docs: describe executive and superuser access"
```

If review corrections changed code, commit each independently testable correction before this documentation commit with a precise `fix:` message.

---

### Task 6: Publish Exact Commit and Deploy Production

**Files:**
- Push: tested worktree `HEAD` to `origin/main`
- Create: `D:\Investment-management\.release-artifacts\<exact SHA>\sd-scm-<exact SHA>-app.tgz`
- Create: `D:\Investment-management\.release-artifacts\<exact SHA>\sd-scm-<exact SHA>-dist.tgz`
- Create: `D:\Investment-management\.release-artifacts\<exact SHA>\sd-scm-<exact SHA>-ops.tgz`
- Create: `/opt/sd-scm/backups/pre-executive-superuser-<exact SHA>.sql`
- Create: `/opt/sd-scm/releases/<exact SHA>/candidate`
- Create: `/opt/sd-scm/releases/<exact SHA>/rollback`
- Modify after acceptance: `README.md`

**Interfaces:**
- Consumes: clean tested release HEAD, production host `root@39.107.52.146`, current production root `/opt/sd-scm`, and insert-only `seed_authorization_catalog`.
- Produces: GitHub `main`, production `REVISION`, and production `RELEASE` pointing to the exact accepted commit; versioned database/application rollback assets; and a final README status commit.

- [ ] **Step 1: Verify local and production preflight state without mutation**

Run locally:

```powershell
$releaseRoot = 'D:\Investment-management\.worktrees\release-unified-org-production-20260813'
$revision = (git -C $releaseRoot rev-parse HEAD).Trim()
git -C $releaseRoot status --short
git -C $releaseRoot fetch origin
git -C $releaseRoot rev-parse origin/main
git -C $releaseRoot merge-base --is-ancestor origin/main $revision
```

Run production read-only checks:

```powershell
ssh -o BatchMode=yes root@39.107.52.146 "cat /opt/sd-scm/REVISION; cat /opt/sd-scm/RELEASE; systemctl is-active sd-scm-backend nginx mysql redis-server; curl -fsS http://127.0.0.1/api/v1/health; df -h /opt/sd-scm; test ! -e /opt/sd-scm/releases/$revision && test ! -e /opt/sd-scm/backups/pre-executive-superuser-$revision.sql"
```

Expected: local status is clean, `origin/main` is an ancestor of the release revision, production still reports the prior healthy release, all four services are active, health is successful, disk space is sufficient, and the versioned candidate/backup paths do not already exist. Stop if any check fails.

- [ ] **Step 2: Push the exact tested commit without force**

```powershell
git -C $releaseRoot push origin HEAD:main
$remoteMain = (git -C $releaseRoot ls-remote origin refs/heads/main).Split()[0]
if ($remoteMain -ne $revision) { throw "origin/main does not match tested revision" }
```

Expected: GitHub `main` equals `$revision`. Do not force-push and do not merge unrelated primary-checkout changes.

- [ ] **Step 3: Build immutable release artifacts from the exact commit**

Rebuild the frontend, create a versioned artifact directory, archive only deployable files, and record hashes:

```powershell
Set-Location "$releaseRoot\frontend"
npm run build
Set-Location $releaseRoot
$artifactRoot = "D:\Investment-management\.release-artifacts\$revision"
New-Item -ItemType Directory -Path $artifactRoot -ErrorAction Stop | Out-Null
tar -czf "$artifactRoot\sd-scm-$revision-app.tgz" -C backend app scripts migrations requirements.txt
tar -czf "$artifactRoot\sd-scm-$revision-dist.tgz" -C frontend\dist .
tar -czf "$artifactRoot\sd-scm-$revision-ops.tgz" deploy README.md
$hashes = Get-FileHash -Algorithm SHA256 "$artifactRoot\sd-scm-$revision-*.tgz"
$hashes | Format-Table Path,Hash
```

Expected: three non-empty archives and three SHA-256 values. Upload with `scp` and compare each local hash to `sha256sum` on the matching `/tmp/` file before extraction.

- [ ] **Step 4: Create production database and application rollback assets**

On the server, create `/opt/sd-scm/releases/$revision/{candidate,rollback}`. Load the existing database credentials from `/opt/sd-scm/backend/.env` without printing them and run `mysqldump --single-transaction --routines --triggers --events --no-tablespaces` to `/opt/sd-scm/backups/pre-executive-superuser-$revision.sql`.

Copy the current versioned backend `app`, `scripts`, `migrations`, `requirements.txt`, frontend `dist`, `deploy`, `README.md`, `REVISION`, and `RELEASE` into the rollback directory. Do not copy or overwrite `.env`, `.venv`, `uploads`, or business data. Verify the SQL dump is non-empty and rollback copies exist before continuing.

- [ ] **Step 5: Stage and preflight the candidate without switching production**

Extract the three verified archives under `/opt/sd-scm/releases/$revision/candidate` and verify:

```bash
cd /opt/sd-scm/backend
PYTHONPATH=/opt/sd-scm/releases/$revision/candidate/backend .venv/bin/python -c 'import app.main'
```

Run the insert-only authorization seeder against a temporary database restored from the production backup first. Query the temporary database and require exactly the three executive positions to have the expected portal/read/export/directory grants and zero forbidden-action grants. Drop the temporary database and revoke its temporary grant in an exit trap. Any SQL/import/query failure stops the release while current production remains active.

- [ ] **Step 6: Enter a short maintenance window and apply the insert-only catalog update**

Enable the existing Nginx maintenance rule for mutating requests while keeping health/read checks available. Run this exact application-level operation from `/opt/sd-scm/backend` with the production virtual environment and candidate code on `PYTHONPATH`:

```bash
PYTHONPATH=/opt/sd-scm/releases/$revision/candidate/backend .venv/bin/python -c 'from app.db.session import SessionLocal; from app.services.organization_catalog import seed_authorization_catalog; db=SessionLocal(); seed_authorization_catalog(db); db.close()'
```

Immediately query `sys_position_permission` joined to `sys_position` and `sys_permission` to verify the expected executive links and no forbidden-action link for those three positions. If verification fails, restore the database backup before removing maintenance mode.

- [ ] **Step 7: Atomically switch application files and restart services**

Prepare same-filesystem `.next.$revision` directories, preserve `.env`, `.venv`, and uploads, then stop `sd-scm-backend`, rename the current backend/frontend versioned directories into the rollback area, rename candidate directories into place, apply `www-data:www-data` ownership, and restart the backend. Run `nginx -t` before reloading Nginx.

If the backend is not active or health does not become successful within 30 seconds, restore the database dump and rollback directories, restart the prior backend, reload the prior Nginx configuration, confirm prior health, and leave `REVISION`/`RELEASE` unchanged.

- [ ] **Step 8: Perform authenticated production acceptance as admin and an executive**

Without logging credentials, verify through the public Nginx endpoint:

1. health returns success;
2. admin portal applications show investment, supply, and fund accessible;
3. admin permission snapshot reports superuser and all registered resources;
4. admin can open user management and click “返回工作平台” to `/`;
5. admin can create/edit/delete a disposable test record and the operation audit records the real admin account;
6. admin can action one disposable active workflow node and `wf_task_action` records the real admin actor plus `system.governance` / `system.superuser`;
7. a disposable second attempt receives the existing 409 task conflict rather than completing twice;
8. an investment executive can list all supply modules and download/export a disposable artifact;
9. the same executive receives HTTP 403 for representative create, update, delete, submit, and approve requests;
10. the organization register displays long names/codes on separate wrapped lines at desktop and narrow widths;
11. `journalctl -u sd-scm-backend --since` the restart contains no unhandled exception, traceback, secret, or repeated 5xx pattern.

Delete only disposable acceptance records through normal application APIs and retain their audit records. Do not alter the admin role or assignments during acceptance.

- [ ] **Step 9: Finalize production markers and remove maintenance mode**

Only after Step 8 passes, write `$revision` to both `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE`, remove the maintenance rule, run `nginx -t`, reload Nginx, and recheck health and all four service states. Confirm:

```powershell
git -C $releaseRoot rev-parse HEAD
git -C $releaseRoot ls-remote origin refs/heads/main
ssh root@39.107.52.146 "cat /opt/sd-scm/REVISION; cat /opt/sd-scm/RELEASE"
```

Expected: all four values are the same exact SHA.

- [ ] **Step 10: Mark README deployed and finalize one release marker**

Change the new README iteration row from `待部署 🟡` to `生产 ✅`, then run:

```powershell
git add -- README.md
git commit -m "docs: mark access fixes deployed"
git push origin HEAD:main
```

Require `git diff --quiet HEAD^ HEAD -- backend frontend deploy` before proceeding, proving this final commit changes only release documentation. Copy the final `/opt/sd-scm/README.md`, set both `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE` to the final documentation commit SHA, and recheck health/services. Because backend, frontend, and deploy files are byte-identical to the already accepted parent, the final marker now represents the complete deployed tree without another service restart. Verify local `HEAD`, GitHub `main`, `REVISION`, and `RELEASE` are all this same final SHA; retain the parent application-artifact SHA in the release report for traceability.

- [ ] **Step 11: Remove only known temporary release helpers**

Delete only the three uploaded `/tmp/sd-scm-$revision-*.tgz` archives after acceptance. Keep the versioned local artifacts, database backup, candidate evidence, rollback directory, and audit records. If a temporary SOCKS tunnel was opened for GitHub access, identify the process by its exact local listening port and stop only that process; confirm the port is no longer listening.

---

## Final Acceptance Checklist

- [ ] All three investment executive positions enter investment, supply, and fund applications.
- [ ] All three investment executive positions have every current supply view/export permission and no write/workflow/configure permission.
- [ ] A representative executive read and download/export succeeds through the real API, while representative create/update/delete/submit/approve calls return HTTP 403.
- [ ] Enabled superusers pass all backend permission and frontend company/resource/permission checks without a fake position or assignment.
- [ ] Disabled superusers receive no bypass.
- [ ] Enabled superusers see/count/action every active designated or shared workflow task, including submit/resubmit, approve, and return.
- [ ] Superuser workflow actions record the real actor/signature and fixed system-governance snapshot.
- [ ] Completed/non-active tasks, invalid actions, invalid returns, and CAS conflicts retain their existing failures.
- [ ] Ordinary user designated/shared-position and duplicate-participation restrictions remain unchanged.
- [ ] Every system-management page exposes “返回工作平台” routing to `/`.
- [ ] Organization-tree names/codes wrap without overlap and row height adapts at desktop and narrow widths.
- [ ] Complete backend tests, complete frontend tests, production frontend build, diff checks, and code review pass.
- [ ] GitHub `main`, deployed code revision markers, production health, service states, database grant query, and audit evidence are verified.
