# Unified Portal, Company Permissions, and Supply Route Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated unified portal, company-role-resource authorization foundation, three application entries, construction pages, and a backward-compatible migration of the current supply-management system to `/supplymanagement`.

**Architecture:** Add a normalized user-company-role table and a deterministic resource-permission registry while retaining `sys_user.role` as the synchronized legacy supply role. The backend remains the authorization authority and exposes portal applications plus the current permission snapshot; the Vue router consumes that snapshot, mounts a shared portal header, and moves every existing supply route under one supply shell with explicit legacy redirects.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2, MySQL 8 SQL migrations, Vue 3.5, Vue Router 4.5, Pinia 2.3, Element Plus 2.9, Vite 6, Vitest 3, Vue Test Utils 2

## Global Constraints

- The product name is exactly `山东出版投资有限公司工作平台` in backend metadata, browser titles, and the global header.
- `/` is the authenticated portal homepage; `/login` remains public.
- The three application routes are exactly `/investment`, `/supplymanagement`, and `/fundmanagement`.
- `/investment` and `/fundmanagement` show `建设中`; only `/supplymanagement` contains the current business system.
- The portal always returns and displays all three applications; permissions disable an application but never hide it.
- Authorization is `company + role + resource`, enforced by the backend before data access; frontend visibility is not a security boundary.
- Existing users are backfilled into `supplymanagement` with their current `sys_user.role`; later edits update the association and the legacy role together.
- `信息维护` and superuser remain one role/account identity: `role=info_maintainer` implies `is_superuser=true`, and a second information-maintainer account is rejected.
- Old supply URLs preserve path parameters, query parameters, and hash fragments when redirected.
- The supply subsystem always provides an `AI 助手` action that returns to `/`.
- The upper portal region is reserved for the AI workspace and the lower region contains three independent application cards; the AI implementation is delivered by the dependent AI plan.
- Do not deploy this plan alone; production release occurs after `2026-08-05-ai-assistant-conversations-tools-streaming.md` also passes.

---

## File Structure

### Backend

- Create `backend/app/models/portal.py`: `UserCompanyRole` persistence model.
- Create `backend/app/schemas/portal.py`: company-role, resource-permission, and portal-application response contracts.
- Create `backend/app/services/permissions.py`: company membership lookup and role-to-resource authorization.
- Create `backend/app/services/portal.py`: immutable three-application registry and per-user access projection.
- Create `backend/app/api/v1/endpoints/portal.py`: portal application and permission APIs.
- Create `backend/migrations/20260805_user_company_roles.sql`: idempotent table creation and one-time supply-role backfill.
- Create `backend/tests/test_company_permissions.py`: permission service and dependency tests.
- Create `backend/tests/test_portal_api.py`: application registry and API response tests.
- Modify `backend/app/core/enums.py`: add stable company and resource codes.
- Modify `backend/app/models/user.py`: add the company-role relationship.
- Modify `backend/app/api/deps.py`: make existing `require_roles` use the supply company association.
- Modify `backend/app/schemas/user.py`: accept and return company-role assignments.
- Modify `backend/app/api/v1/endpoints/user.py`: atomically maintain assignments and legacy supply role.
- Modify `backend/app/api/v1/endpoints/auth.py`: return company roles in the current-user payload.
- Modify `backend/app/api/v1/router.py`: register the portal router.
- Modify `backend/app/db/init_db.py`: register the model and seed missing associations without overwriting edits.
- Modify `backend/app/core/config.py`: change the product name.

### Frontend

- Create `frontend/src/api/portal.js`: portal applications and permission snapshot client.
- Create `frontend/src/store/portal.js`: cached portal applications and current permissions.
- Create `frontend/src/components/GlobalHeader.vue`: shared product header, theme, user menu, and portal/AI action.
- Create `frontend/src/layout/PortalLayout.vue`: global header and portal content shell.
- Create `frontend/src/views/portal/index.vue`: upper AI mount region and lower application entry region.
- Create `frontend/src/views/portal/ConstructionView.vue`: shared investment/fund construction page.
- Create `frontend/src/components/portal/ApplicationEntry.vue`: one application card with live, construction, and denied states.
- Create `frontend/src/router/legacyRedirects.js`: explicit old-to-new redirect records.
- Create `frontend/src/router/routes.test.js`: route migration and redirect contract tests.
- Create `frontend/src/store/portal.test.js`: permission snapshot/store tests.
- Create `frontend/src/views/portal/index.test.js`: portal layout and entry-state tests.
- Create `frontend/src/test/setup.js`: Vitest DOM cleanup setup.
- Modify `frontend/package.json` and `frontend/package-lock.json`: add the frontend test toolchain.
- Modify `frontend/vite.config.js`: add the Vitest `happy-dom` configuration.
- Modify `frontend/src/router/index.js`: mount portal and supply route trees.
- Modify `frontend/src/permission.js`: guard company and role resources from the backend snapshot.
- Modify `frontend/src/store/user.js`: use the supply company role instead of local legacy-role authorization.
- Modify `frontend/src/layout/index.vue`: become the supply-only shell and reuse `GlobalHeader`.
- Modify `frontend/src/constants/business.js`: prefix allowed supply paths.
- Modify `frontend/src/views/cultural-tourism/MainView.vue`: use the prefixed detail route.
- Modify `frontend/src/views/cultural-tourism/DetailView.vue`: use the prefixed parent route.
- Modify `frontend/src/components/screen/DataScreen.vue`: use the prefixed screen route.
- Modify `frontend/src/styles/_tokens.scss`: add portal layout tokens while preserving the existing palette.
- Modify `frontend/src/styles/index.scss`: add shared portal page sizing and mobile overflow rules.

---

### Task 1: Persist Company Roles and Backfill Existing Users

**Files:**
- Create: `backend/app/models/portal.py`
- Create: `backend/migrations/20260805_user_company_roles.sql`
- Create: `backend/tests/test_company_permissions.py`
- Modify: `backend/app/core/enums.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/db/init_db.py`

**Interfaces:**
- Produces: `CompanyCode`, `ResourceCode`, and `UserCompanyRole(user_id: int, company_code: str, role: Role)`.
- Produces: unique membership key `(user_id, company_code)` and relationship `User.company_roles`.
- Preserves: `User.role` as the legacy `supplymanagement` role only.

- [ ] **Step 1: Write the failing model and migration contract tests**

```python
# backend/tests/test_company_permissions.py
import unittest

from app.core.enums import CompanyCode, ResourceCode
from app.models.portal import UserCompanyRole


class CompanyRoleModelTest(unittest.TestCase):
    def test_company_and_resource_codes_are_stable(self):
        self.assertEqual(CompanyCode.INVESTMENT.value, "investment")
        self.assertEqual(CompanyCode.SUPPLY_MANAGEMENT.value, "supplymanagement")
        self.assertEqual(CompanyCode.FUND_MANAGEMENT.value, "fundmanagement")
        self.assertEqual(ResourceCode.SCENIC_ANALYTICS.value, "supply.scenic.analytics")

    def test_user_company_role_has_one_membership_per_company(self):
        unique_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in UserCompanyRole.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("user_id", "company_code"), unique_sets)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify the missing domain types fail**

Run: `cd backend; python -m unittest tests.test_company_permissions.CompanyRoleModelTest -v`

Expected: FAIL with an import error for `CompanyCode` or `app.models.portal`.

- [ ] **Step 3: Add the enums, model, relationship, and idempotent migration**

```python
# backend/app/core/enums.py
class CompanyCode(str, Enum):
    INVESTMENT = "investment"
    SUPPLY_MANAGEMENT = "supplymanagement"
    FUND_MANAGEMENT = "fundmanagement"


class ResourceCode(str, Enum):
    PORTAL = "portal"
    SUPPLY_DASHBOARD = "supply.dashboard"
    SUPPLY_OPERATION = "supply.operation"
    SCENIC_ANALYTICS = "supply.scenic.analytics"
    SUPPLY_FINANCE = "supply.finance"
    SUPPLY_CONTRACT = "supply.contract"
    SUPPLY_APPROVAL = "supply.approval"
    SUPPLY_CUSTOMER = "supply.customer"
    SUPPLY_ADMIN = "supply.admin"
```

```python
# backend/app/models/portal.py
from sqlalchemy import Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Role
from app.db.base import Base


class UserCompanyRole(Base):
    __tablename__ = "sys_user_company_role"
    __table_args__ = (
        UniqueConstraint("user_id", "company_code", name="uq_user_company_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=32, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    user = relationship("User", back_populates="company_roles")
```

The SQL migration must use `CREATE TABLE IF NOT EXISTS` and this non-overwriting backfill:

```sql
INSERT IGNORE INTO sys_user_company_role (user_id, company_code, role)
SELECT id, 'supplymanagement', role FROM sys_user;
```

In `seed_users`, flush users and insert only a missing `supplymanagement` association. Never update an existing association during startup.

- [ ] **Step 4: Run model tests and the existing backend suite**

Run: `cd backend; python -m unittest tests.test_company_permissions.CompanyRoleModelTest -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all existing tests PASS.

- [ ] **Step 5: Commit the persistence boundary**

```bash
git add backend/app/core/enums.py backend/app/models/portal.py backend/app/models/user.py backend/app/db/init_db.py backend/migrations/20260805_user_company_roles.sql backend/tests/test_company_permissions.py
git commit -m "feat: add company role memberships"
```

### Task 2: Make Company Roles the Backend Authorization Authority

**Files:**
- Create: `backend/app/services/permissions.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/tests/test_company_permissions.py`

**Interfaces:**
- Consumes: `UserCompanyRole`, `CompanyCode`, `ResourceCode`, and current `Role` values.
- Produces: `get_company_role(db: Session, user: User, company: CompanyCode) -> Role | None`.
- Produces: `allowed_resources(db: Session, user: User, company: CompanyCode) -> frozenset[ResourceCode]`.
- Produces: `has_resource(db, user, company, resource) -> bool` and `require_company_resource(company, resource)`.
- Changes: `require_roles(*roles)` authorizes against the user's `supplymanagement` association, with only `is_superuser` bypassing lookup.

- [ ] **Step 1: Add failing authorization tests**

```python
# append to backend/tests/test_company_permissions.py
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.enums import CompanyCode, ResourceCode, Role
from app.services.permissions import allowed_resources, get_company_role, has_resource


class CompanyPermissionServiceTest(unittest.TestCase):
    def test_supply_membership_overrides_stale_legacy_role(self):
        user = SimpleNamespace(id=7, role=Role.LEGAL_COUNSEL, is_superuser=False)
        db = Mock()
        db.scalar.return_value = Role.BUSINESS_HANDLER
        self.assertEqual(
            get_company_role(db, user, CompanyCode.SUPPLY_MANAGEMENT),
            Role.BUSINESS_HANDLER,
        )

    def test_user_without_company_membership_has_no_supply_resource(self):
        user = SimpleNamespace(id=8, role=Role.BUSINESS_HANDLER, is_superuser=False)
        db = Mock()
        db.scalar.return_value = None
        self.assertFalse(
            has_resource(db, user, CompanyCode.SUPPLY_MANAGEMENT, ResourceCode.SCENIC_ANALYTICS)
        )

    def test_superuser_has_all_registered_resources(self):
        user = SimpleNamespace(id=1, is_superuser=True)
        resources = allowed_resources(Mock(), user, CompanyCode.SUPPLY_MANAGEMENT)
        self.assertIn(ResourceCode.SUPPLY_ADMIN, resources)
        self.assertIn(ResourceCode.SCENIC_ANALYTICS, resources)
```

- [ ] **Step 2: Run the permission tests and verify failure**

Run: `cd backend; python -m unittest tests.test_company_permissions.CompanyPermissionServiceTest -v`

Expected: FAIL because `app.services.permissions` does not exist.

- [ ] **Step 3: Implement the static role-resource registry and dependencies**

```python
# backend/app/services/permissions.py
SUPPLY_RESOURCE_ROLES: dict[ResourceCode, frozenset[Role]] = {
    ResourceCode.SUPPLY_DASHBOARD: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_OPERATION: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SCENIC_ANALYTICS: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_FINANCE: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.FINANCE_HANDLER,
        Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_CONTRACT: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.SCM_DIRECTOR, Role.INVEST_DIRECTOR, Role.LEGAL_COUNSEL,
    }),
    ResourceCode.SUPPLY_APPROVAL: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_CUSTOMER: frozenset({
        Role.BUSINESS_HANDLER, Role.BUSINESS_REVIEWER, Role.RISK_AUDITOR,
        Role.FINANCE_HANDLER, Role.FINANCE_REVIEWER, Role.SCM_DIRECTOR,
        Role.INVEST_DIRECTOR,
    }),
    ResourceCode.SUPPLY_ADMIN: frozenset({Role.INFO_MAINTAINER}),
}
```

Query only `UserCompanyRole.role` for the requested company. Return all resources for superusers. Update `require_roles` to inject `Session`, resolve `CompanyCode.SUPPLY_MANAGEMENT`, and return HTTP 403 when the association is absent or its role is not allowed. Do not fall back to `User.role`.

- [ ] **Step 4: Run permission and endpoint regression tests**

Run: `cd backend; python -m unittest tests.test_company_permissions -v`

Expected: PASS, including stale legacy-role and missing-membership cases.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the authorization switch**

```bash
git add backend/app/services/permissions.py backend/app/api/deps.py backend/tests/test_company_permissions.py
git commit -m "feat: authorize supply resources by company role"
```

### Task 3: Expose the Portal Application Registry and Permission Snapshot

**Files:**
- Create: `backend/app/schemas/portal.py`
- Create: `backend/app/services/portal.py`
- Create: `backend/app/api/v1/endpoints/portal.py`
- Create: `backend/tests/test_portal_api.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- Produces: `GET /api/v1/portal/applications -> Response[list[PortalApplicationOut]]`.
- Produces: `GET /api/v1/portal/me/permissions -> Response[PortalPermissionSnapshot]`.
- `PortalApplicationOut`: `code`, `company_name`, `route`, `status`, `accessible`, `denial_reason`.
- `PortalPermissionSnapshot`: `is_superuser`, `company_roles`, `resources`.

- [ ] **Step 1: Write failing registry tests**

```python
# backend/tests/test_portal_api.py
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.enums import CompanyCode, Role
from app.services.portal import applications_for_user


class PortalRegistryTest(unittest.TestCase):
    @patch("app.services.portal.get_company_role")
    def test_registry_always_returns_three_apps_in_fixed_order(self, company_role):
        company_role.side_effect = lambda db, user, company: (
            Role.BUSINESS_HANDLER if company == CompanyCode.SUPPLY_MANAGEMENT else None
        )
        apps = applications_for_user(Mock(), SimpleNamespace(is_superuser=False))
        self.assertEqual([item.code for item in apps], [
            "investment", "supplymanagement", "fundmanagement"
        ])
        self.assertEqual([item.status for item in apps], ["construction", "online", "construction"])
        self.assertEqual([item.accessible for item in apps], [False, True, False])

    def test_product_name_is_unified(self):
        from app.core.config import Settings
        self.assertEqual(Settings().PROJECT_NAME, "山东出版投资有限公司工作平台")
```

- [ ] **Step 2: Run the registry tests and verify failure**

Run: `cd backend; python -m unittest tests.test_portal_api -v`

Expected: FAIL because the portal schema/service is missing and the old project name is still configured.

- [ ] **Step 3: Implement the registry, schemas, and authenticated endpoints**

```python
# backend/app/services/portal.py
APPLICATIONS = (
    ("investment", "山东出版投资有限公司", "/investment", "construction"),
    ("supplymanagement", "山东出版供应链管理有限公司", "/supplymanagement", "online"),
    ("fundmanagement", "山东出版股权基金管理有限公司", "/fundmanagement", "construction"),
)
```

For each item, set `accessible=true` only for superusers or users with that company membership. Set `denial_reason="暂时无访问权限"` for denied applications. Construction status remains `construction` even when accessible. The permissions endpoint serializes role values and sorted resource codes; it never accepts a target user ID from the client.

Register the endpoints with:

```python
api_router.include_router(portal.router, prefix="/portal", tags=["统一门户"])
```

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd backend; python -m unittest tests.test_portal_api tests.test_company_permissions -v`

Expected: PASS.

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit the portal API**

```bash
git add backend/app/schemas/portal.py backend/app/services/portal.py backend/app/api/v1/endpoints/portal.py backend/app/api/v1/router.py backend/app/core/config.py backend/tests/test_portal_api.py
git commit -m "feat: expose unified portal applications"
```

### Task 4: Keep User Administration and Legacy Roles Synchronized

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/api/v1/endpoints/user.py`
- Modify: `backend/app/api/v1/endpoints/auth.py`
- Modify: `backend/tests/test_company_permissions.py`
- Modify: `frontend/src/api/user.js`
- Modify: `frontend/src/views/system/users.vue`

**Interfaces:**
- Produces: `CompanyRoleAssignment(company_code: CompanyCode, role: Role)`.
- Changes: `UserCreate.company_roles` and `UserUpdate.company_roles` use a list unique by company.
- Changes: `UserOut.company_roles` and `UserBrief.company_roles` return the authoritative associations.
- Guarantees: changing the `supplymanagement` assignment changes `User.role` in the same transaction.

- [ ] **Step 1: Add failing synchronization and information-maintainer tests**

```python
# append to backend/tests/test_company_permissions.py
from app.schemas.user import CompanyRoleAssignment, UserCreate


class UserCompanyRoleSchemaTest(unittest.TestCase):
    def test_duplicate_company_assignments_are_rejected(self):
        with self.assertRaises(ValueError):
            UserCreate(
                username="worker", full_name="测试", password="123456",
                company_roles=[
                    CompanyRoleAssignment(company_code="supplymanagement", role="business_handler"),
                    CompanyRoleAssignment(company_code="supplymanagement", role="finance_handler"),
                ],
            )

    def test_info_maintainer_cannot_be_created_as_a_normal_user(self):
        with self.assertRaises(ValueError):
            UserCreate(
                username="admin2", full_name="第二管理员", password="123456",
                role="info_maintainer", is_superuser=False,
                company_roles=[],
            )
```

- [ ] **Step 2: Run the schema tests and verify failure**

Run: `cd backend; python -m unittest tests.test_company_permissions.UserCompanyRoleSchemaTest -v`

Expected: FAIL because `CompanyRoleAssignment` and the validation rules do not exist.

- [ ] **Step 3: Implement atomic assignment replacement and the single admin identity rule**

```python
# backend/app/schemas/user.py
class CompanyRoleAssignment(BaseModel):
    company_code: CompanyCode
    role: Role


class UserCreate(UserBase):
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)
    is_superuser: bool = False
    company_roles: list[CompanyRoleAssignment] = Field(default_factory=list)
```

Add Pydantic model validators that reject duplicate company codes and reject mismatched `role=info_maintainer` / `is_superuser`. In the endpoint service path:

1. Reject creating another `Role.INFO_MAINTAINER` when one already exists.
2. Replace associations inside the same DB transaction as the user update.
3. Require one `supplymanagement` assignment for every non-superuser currently managed through this screen.
4. Copy that assignment's role to `user.role` before commit.
5. For the existing information maintainer, keep `role=INFO_MAINTAINER` and `is_superuser=true`; global access does not require three synthetic memberships.

Update the user table/dialog to edit one role selector per company. Render the information-maintainer row as `信息维护（超级管理员）` and disable its role/superuser identity controls.

- [ ] **Step 4: Run backend tests and build the frontend**

Run: `cd backend; python -m unittest tests.test_company_permissions -v`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: Vite exits 0 and emits `dist/index.html`.

- [ ] **Step 5: Commit synchronized user administration**

```bash
git add backend/app/schemas/user.py backend/app/api/v1/endpoints/user.py backend/app/api/v1/endpoints/auth.py backend/tests/test_company_permissions.py frontend/src/api/user.js frontend/src/views/system/users.vue
git commit -m "feat: manage users by company role"
```

### Task 5: Add Frontend Test Infrastructure and the Portal Permission Store

**Files:**
- Create: `frontend/src/api/portal.js`
- Create: `frontend/src/store/portal.js`
- Create: `frontend/src/store/portal.test.js`
- Create: `frontend/src/test/setup.js`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.js`
- Modify: `frontend/src/store/user.js`

**Interfaces:**
- Produces: `getPortalApplications()` and `getMyPortalPermissions()`.
- Produces: Pinia store actions `loadPortalContext(force = false)` and `clearPortalContext()`.
- Produces: computed `companyRole(companyCode)`, `hasCompany(companyCode)`, and `hasResource(resourceCode)`.

- [ ] **Step 1: Install and configure the frontend test runner**

Run: `cd frontend; npm install --save-dev vitest@^3.2.4 @vue/test-utils@^2.4.6 happy-dom@^17.6.3`

Add `"test": "vitest run"` to scripts and this Vite configuration:

```javascript
test: {
  environment: 'happy-dom',
  globals: true,
  setupFiles: ['./src/test/setup.js']
}
```

Expected: `package.json` and `package-lock.json` change; `npm run test -- --help` exits 0.

- [ ] **Step 2: Write the failing store tests**

```javascript
// frontend/src/store/portal.test.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePortalStore } from './portal'
import * as portalApi from '@/api/portal'

vi.mock('@/api/portal')

describe('portal store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads applications and resolves the supply company role', async () => {
    portalApi.getPortalApplications.mockResolvedValue([{ code: 'supplymanagement', accessible: true }])
    portalApi.getMyPortalPermissions.mockResolvedValue({
      is_superuser: false,
      company_roles: [{ company_code: 'supplymanagement', role: 'business_handler' }],
      resources: ['supply.scenic.analytics']
    })
    const store = usePortalStore()
    await store.loadPortalContext()
    expect(store.companyRole('supplymanagement')).toBe('business_handler')
    expect(store.hasResource('supply.scenic.analytics')).toBe(true)
  })
})
```

- [ ] **Step 3: Run the store test and verify failure**

Run: `cd frontend; npm test -- src/store/portal.test.js`

Expected: FAIL because `usePortalStore` and the portal API client do not exist.

- [ ] **Step 4: Implement the API/store and connect logout cleanup**

```javascript
// frontend/src/api/portal.js
import request from './request'

export const getPortalApplications = () => request.get('/portal/applications')
export const getMyPortalPermissions = () => request.get('/portal/me/permissions')
```

The store must deduplicate simultaneous loads with one in-flight promise, cache only for the current login, and reset on logout. Change `useUserStore.hasRole(roles)` to evaluate the role returned by `portalStore.companyRole('supplymanagement')`; keep the superuser bypass.

Run: `cd frontend; npm test -- src/store/portal.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the frontend authorization state**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src/test/setup.js frontend/src/api/portal.js frontend/src/store/portal.js frontend/src/store/portal.test.js frontend/src/store/user.js
git commit -m "test: add portal permission store coverage"
```

### Task 6: Migrate Supply Routes and Preserve Every Legacy URL

**Files:**
- Create: `frontend/src/router/legacyRedirects.js`
- Create: `frontend/src/router/routes.test.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/constants/business.js`
- Modify: `frontend/src/permission.js`

**Interfaces:**
- Produces named route `PortalHome` at `/`.
- Produces named supply routes under `/supplymanagement/*`.
- Produces `legacySupplyRedirects` with function redirects that copy `params`, `query`, and `hash`.
- Requires route meta `company`, `resource`, `roles`, and `requiresSuperuser` as applicable.

- [ ] **Step 1: Write failing route contract tests**

```javascript
// frontend/src/router/routes.test.js
import { describe, expect, it } from 'vitest'
import router from './index'

describe('unified portal routes', () => {
  it('mounts the supply detail under the supply namespace', () => {
    const resolved = router.resolve('/supplymanagement/cultural-tourism/zunyi-zoo?tab=ticket')
    expect(resolved.name).toBe('CulturalTourismDetail')
    expect(resolved.params.scenicId).toBe('zunyi-zoo')
    expect(resolved.query.tab).toBe('ticket')
  })

  it('redirects a legacy dynamic route without losing query or hash', async () => {
    await router.push('/cultural-tourism/zunyi-zoo?tab=hotel#ledger')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe(
      '/supplymanagement/cultural-tourism/zunyi-zoo?tab=hotel#ledger'
    )
  })
})
```

- [ ] **Step 2: Run route tests and verify failure**

Run: `cd frontend; npm test -- src/router/routes.test.js`

Expected: FAIL because supply routes still resolve at their old locations.

- [ ] **Step 3: Build the portal/supply route trees and explicit redirects**

```javascript
// frontend/src/router/legacyRedirects.js
const redirectTo = (name) => (to) => ({
  name,
  params: to.params,
  query: to.query,
  hash: to.hash,
  replace: true
})

export const legacySupplyRedirects = [
  { path: '/dashboard', redirect: redirectTo('Dashboard') },
  { path: '/operation', redirect: redirectTo('Operation') },
  { path: '/cultural-tourism', redirect: redirectTo('CulturalTourism') },
  { path: '/cultural-tourism/:scenicId', redirect: redirectTo('CulturalTourismDetail') },
  { path: '/channel', redirect: redirectTo('CulturalTourism') },
  { path: '/channel/tourism', redirect: redirectTo('CulturalTourism') },
  { path: '/channel/other', redirect: redirectTo('CulturalTourism') },
  { path: '/finance/fund', redirect: redirectTo('FinanceFund') },
  { path: '/finance/invoice', redirect: redirectTo('Invoice') },
  { path: '/invoice', redirect: redirectTo('Invoice') },
  { path: '/contract', redirect: redirectTo('Contract') },
  { path: '/approval', redirect: redirectTo('Approval') },
  { path: '/customer', redirect: redirectTo('Customer') },
  { path: '/org', redirect: redirectTo('Org') },
  { path: '/audit', redirect: redirectTo('Audit') },
  { path: '/profile', redirect: redirectTo('Profile') },
  { path: '/screen', redirect: redirectTo('Screen') }
]
```

Mount supply children under `{ path: '/supplymanagement', component: () => import('@/layout/index.vue'), redirect: '/supplymanagement/dashboard' }`. Mount the screen at `/supplymanagement/screen`. Give every supply route `meta.company='supplymanagement'` and the resource matching the backend registry.

The global guard must load the portal context after authentication, reject inaccessible companies to `/`, and then enforce `meta.resource`, `meta.roles`, and `requiresSuperuser`. Change all guard fallbacks from `/dashboard` or `/contract` to their prefixed equivalents.

- [ ] **Step 4: Run route tests and a production build**

Run: `cd frontend; npm test -- src/router/routes.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: Vite exits 0 with no unresolved route imports.

- [ ] **Step 5: Commit the route migration**

```bash
git add frontend/src/router/index.js frontend/src/router/legacyRedirects.js frontend/src/router/routes.test.js frontend/src/constants/business.js frontend/src/permission.js
git commit -m "feat: move supply routes under unified portal"
```

### Task 7: Share the Global Header and Repair Internal Supply Navigation

**Files:**
- Create: `frontend/src/components/GlobalHeader.vue`
- Create: `frontend/src/layout/PortalLayout.vue`
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/views/cultural-tourism/MainView.vue`
- Modify: `frontend/src/views/cultural-tourism/DetailView.vue`
- Modify: `frontend/src/components/screen/DataScreen.vue`
- Modify: `frontend/src/components/UserDropdown.vue`

**Interfaces:**
- Produces: `GlobalHeader` props `contextLabel: string` and `showAssistantAction: boolean`.
- Produces: event-free navigation to route name `PortalHome` from the assistant action.
- Changes: all programmatic supply navigation uses named routes or `/supplymanagement/*` paths.

- [ ] **Step 1: Add failing navigation assertions**

Extend `frontend/src/router/routes.test.js`:

```javascript
it('keeps the portal and supply profile destinations distinct', () => {
  expect(router.resolve({ name: 'PortalHome' }).path).toBe('/')
  expect(router.resolve({ name: 'Profile' }).path).toBe('/supplymanagement/profile')
  expect(router.resolve({ name: 'Screen' }).path).toBe('/supplymanagement/screen')
})
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd frontend; npm test -- src/router/routes.test.js`

Expected: FAIL until the named routes and supply navigation are aligned.

- [ ] **Step 3: Extract the header and update all internal links**

`GlobalHeader.vue` must render `山东出版投资有限公司工作平台`, an optional context label, `ThemeToggle`, `UserDropdown`, and a `ChatDotRound` icon button labeled `AI 助手` when inside supply. Its click uses:

```javascript
const router = useRouter()
const openAssistant = () => router.push({ name: 'PortalHome' })
```

Change supply menu item indices to each child's absolute resolved path. Replace the three known hard-coded paths:

```javascript
router.push({ name: 'CulturalTourismDetail', params: { scenicId: id } })
router.push({ name: 'CulturalTourism' })
router.push({ name: 'Screen' })
```

Make `UserDropdown` use `{ name: 'Profile' }` and clear both user and portal stores on logout.

- [ ] **Step 4: Run tests and build**

Run: `cd frontend; npm test -- src/router/routes.test.js src/store/portal.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit the shared shell**

```bash
git add frontend/src/components/GlobalHeader.vue frontend/src/layout/PortalLayout.vue frontend/src/layout/index.vue frontend/src/views/cultural-tourism/MainView.vue frontend/src/views/cultural-tourism/DetailView.vue frontend/src/components/screen/DataScreen.vue frontend/src/components/UserDropdown.vue
git commit -m "feat: add shared portal and supply header"
```

### Task 8: Build the Portal Home and Construction Pages

**Files:**
- Create: `frontend/src/components/portal/ApplicationEntry.vue`
- Create: `frontend/src/views/portal/index.vue`
- Create: `frontend/src/views/portal/ConstructionView.vue`
- Create: `frontend/src/views/portal/index.test.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/styles/_tokens.scss`
- Modify: `frontend/src/styles/index.scss`

**Interfaces:**
- `ApplicationEntry` consumes one backend `PortalApplicationOut` and emits `open(route)` only when `status='online' && accessible=true`.
- `PortalHome` loads portal context and renders the AI region before the application region.
- `ConstructionView` consumes route meta `companyName` and always renders `建设中`.

- [ ] **Step 1: Write failing portal rendering tests**

```javascript
// frontend/src/views/portal/index.test.js
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PortalHome from './index.vue'

vi.mock('@/store/portal', () => ({
  usePortalStore: () => ({
    applications: [
      { code: 'investment', company_name: '山东出版投资有限公司', route: '/investment', status: 'construction', accessible: true },
      { code: 'supplymanagement', company_name: '山东出版供应链管理有限公司', route: '/supplymanagement', status: 'online', accessible: true },
      { code: 'fundmanagement', company_name: '山东出版股权基金管理有限公司', route: '/fundmanagement', status: 'construction', accessible: false, denial_reason: '暂时无访问权限' }
    ],
    loadPortalContext: vi.fn()
  })
}))

describe('portal home', () => {
  it('renders the assistant region before exactly three application entries', () => {
    const wrapper = mount(PortalHome, { global: { stubs: ['el-skeleton', 'router-link'] } })
    expect(wrapper.find('[data-testid="assistant-region"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="application-entry"]')).toHaveLength(3)
    expect(wrapper.find('[data-testid="assistant-region"]').element.compareDocumentPosition(
      wrapper.find('[data-testid="application-region"]').element
    ) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run the portal tests and verify failure**

Run: `cd frontend; npm test -- src/views/portal/index.test.js`

Expected: FAIL because the portal views do not exist.

- [ ] **Step 3: Implement the responsive portal views**

The home view must use this semantic order:

```vue
<main class="portal-home">
  <section data-testid="assistant-region" class="assistant-region" aria-label="AI 智能助手">
    <el-skeleton :rows="5" animated />
  </section>
  <section data-testid="application-region" class="application-region" aria-label="业务系统">
    <ApplicationEntry
      v-for="application in portalStore.applications"
      :key="application.code"
      :application="application"
      @open="router.push($event)"
    />
  </section>
</main>
```

Use a fixed desktop assistant height that leaves the complete application heading and the top of all three entries visible at 1440x900. Use three equal grid columns above 960px and one column below 720px. Keep entry radii at 8px, prevent long company names from overflowing, and do not nest cards. Construction entries show `建设中`; denied entries also show `暂时无访问权限` and do not navigate.

Register `/investment` and `/fundmanagement` as children of `PortalLayout` with `companyName` metadata. Direct access to a denied company is rejected by the guard before the view renders.

- [ ] **Step 4: Run portal tests and build**

Run: `cd frontend; npm test -- src/views/portal/index.test.js src/router/routes.test.js`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS with the portal and construction chunks emitted.

- [ ] **Step 5: Commit the portal UI**

```bash
git add frontend/src/components/portal/ApplicationEntry.vue frontend/src/views/portal/index.vue frontend/src/views/portal/ConstructionView.vue frontend/src/views/portal/index.test.js frontend/src/router/index.js frontend/src/styles/_tokens.scss frontend/src/styles/index.scss
git commit -m "feat: build unified business portal"
```

### Task 9: Verify Migration Safety and Prepare the AI Plan Boundary

**Files:**
- Modify: `backend/tests/test_portal_api.py`
- Modify: `frontend/src/router/routes.test.js`
- Modify: `docs/superpowers/specs/2026-08-05-unified-ai-portal-phase-1-design.md` only if implementation reveals a factual contradiction; otherwise leave it unchanged.

**Interfaces:**
- Verifies: no old URL loses `params`, `query`, or `hash`.
- Verifies: portal responses always contain three applications.
- Verifies: every supply API is denied when the supply membership is absent.
- Hands off: stable `PortalHome`, `PortalLayout`, `GlobalHeader`, `usePortalStore`, and permission-service interfaces to the AI plan.

- [ ] **Step 1: Add table-driven redirect and direct-API denial regressions**

```javascript
// append to frontend/src/router/routes.test.js
it.each([
  ['/dashboard?year=2026', '/supplymanagement/dashboard?year=2026'],
  ['/finance/invoice?status=pending', '/supplymanagement/finance/invoice?status=pending'],
  ['/screen#map', '/supplymanagement/screen#map']
])('preserves legacy location %s', async (legacy, expected) => {
  await router.push(legacy)
  expect(router.currentRoute.value.fullPath).toBe(expected)
})
```

Add a backend dependency test that invokes the `require_roles(Role.BUSINESS_HANDLER)` checker with a non-superuser whose association lookup returns `None` and asserts HTTP 403.

- [ ] **Step 2: Run all focused portal, permission, and route tests**

Run: `cd backend; python -m unittest tests.test_company_permissions tests.test_portal_api -v`

Expected: PASS.

Run: `cd frontend; npm test -- src/store/portal.test.js src/router/routes.test.js src/views/portal/index.test.js`

Expected: PASS.

- [ ] **Step 3: Run full regression suites**

Run: `cd backend; python -m unittest discover -s tests -v`

Expected: all backend tests PASS.

Run: `cd frontend; npm test`

Expected: all frontend tests PASS.

- [ ] **Step 4: Run the production build and inspect repository scope**

Run: `cd frontend; npm run build`

Expected: Vite exits 0.

Run: `git status --short`

Expected: only files from this plan and pre-existing unrelated user changes are present; no generated `frontend/dist` files are staged.

- [ ] **Step 5: Commit final plan-one regressions**

```bash
git add backend/tests/test_company_permissions.py backend/tests/test_portal_api.py frontend/src/router/routes.test.js
git commit -m "test: verify portal migration boundaries"
```

---

## Plan-One Completion Gate

- [ ] `sys_user_company_role` migration has run against a production snapshot and does not overwrite a previously edited association.
- [ ] Existing supply API authorization uses the `supplymanagement` association and rejects missing membership.
- [ ] The information-maintainer account is still the sole superuser identity.
- [ ] The portal returns and displays exactly three systems with correct access and construction states.
- [ ] Every current supply page works below `/supplymanagement`.
- [ ] Old static and dynamic URLs retain query strings and fragments.
- [ ] Desktop and mobile portal layouts contain no overlapping controls or text.
- [ ] Backend tests, frontend tests, and the production frontend build pass.
