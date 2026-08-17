# Current Assignment Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy-role labels in the shared header and profile with every current effective normalized assignment.

**Architecture:** Add one pure frontend formatter that selects the authoritative portal assignment snapshot after it loads and otherwise filters the login user's assignment summaries. Both display components consume the same formatter, while backend assignment storage and authorization remain unchanged.

**Tech Stack:** Vue 3, Pinia, Vitest, Vue Test Utils, Vite

## Global Constraints

- Show each assignment as `组织名称 / 岗位名称`.
- Join every unique effective assignment with the Chinese delimiter `、`.
- Show `未配置岗位` only when a non-superuser has no current effective assignment.
- Keep the superuser label as `信息维护`.
- Do not change the database schema, assignment write endpoint, legacy `sys_user.role`, or permission calculation.
- Treat the loaded portal permission snapshot as authoritative; use login-user summaries only before that snapshot is loaded.

---

### Task 1: Pure current-assignment display formatter

**Files:**
- Create: `frontend/src/utils/assignmentDisplay.js`
- Test: `frontend/src/utils/assignmentDisplay.test.js`

**Interfaces:**
- Consumes: portal assignment objects and `UserOut.assignment_summaries` objects containing `organization_name`, `position_name`, optional `status`, `valid_from`, and `valid_until`.
- Produces: `currentAssignmentLabel(options: AssignmentDisplayOptions): string`.

- [ ] **Step 1: Write the failing formatter tests**

```js
import { describe, expect, it } from 'vitest'
import { currentAssignmentLabel } from './assignmentDisplay'

const assignment = (overrides = {}) => ({
  organization_name: '法务风控部',
  position_name: '部门副总监',
  status: 'active',
  valid_from: '2026-08-01',
  valid_until: '2036-08-01',
  ...overrides
})

describe('currentAssignmentLabel', () => {
  it('formats the loaded portal assignment snapshot', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [assignment({ status: undefined })],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监')
  })

  it('shows every unique effective assignment', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [
        assignment({ status: undefined }),
        assignment({ organization_name: '资产财务部', position_name: '财务复核', status: undefined }),
        assignment({ status: undefined })
      ],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监、资产财务部 / 财务复核')
  })

  it('filters inactive, future and expired fallback summaries', () => {
    expect(currentAssignmentLabel({
      userAssignments: [
        assignment(),
        assignment({ position_name: '停用岗位', status: 'inactive' }),
        assignment({ position_name: '未来岗位', valid_from: '2026-09-01' }),
        assignment({ position_name: '过期岗位', valid_until: '2026-08-16' })
      ],
      today: '2026-08-17'
    })).toBe('法务风控部 / 部门副总监')
  })

  it('does not reuse fallback summaries after an empty portal snapshot loads', () => {
    expect(currentAssignmentLabel({
      portalLoaded: true,
      portalAssignments: [],
      userAssignments: [assignment()],
      today: '2026-08-17'
    })).toBe('未配置岗位')
  })

  it('keeps the information-maintainer label for superuser', () => {
    expect(currentAssignmentLabel({
      isSuperuser: true,
      superuserLabel: '信息维护',
      portalLoaded: true,
      portalAssignments: []
    })).toBe('信息维护')
  })
})
```

- [ ] **Step 2: Run the formatter test and verify it fails**

Run: `cd frontend && npm test -- src/utils/assignmentDisplay.test.js`

Expected: FAIL because `./assignmentDisplay` does not exist.

- [ ] **Step 3: Implement the minimal pure formatter**

```js
const dateKey = (value = new Date()) => {
  if (typeof value === 'string') return value
  const pad = (part) => String(part).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

const isEffective = (assignment, today) => {
  if (assignment?.status && assignment.status !== 'active') return false
  if (assignment?.valid_from && assignment.valid_from > today) return false
  if (assignment?.valid_until && assignment.valid_until < today) return false
  return true
}

const assignmentLabel = (assignment) => {
  const organization = assignment?.organization_name?.trim()
  const position = assignment?.position_name?.trim()
  return organization && position ? `${organization} / ${position}` : ''
}

export function currentAssignmentLabel({
  portalAssignments = [],
  portalLoaded = false,
  userAssignments = [],
  isSuperuser = false,
  superuserLabel = '信息维护',
  today = dateKey()
} = {}) {
  if (isSuperuser) return superuserLabel || '信息维护'
  const source = portalLoaded ? portalAssignments : userAssignments
  const labels = [...new Set(
    source.filter((item) => isEffective(item, today)).map(assignmentLabel).filter(Boolean)
  )]
  return labels.length ? labels.join('、') : '未配置岗位'
}
```

- [ ] **Step 4: Run the formatter test and verify it passes**

Run: `cd frontend && npm test -- src/utils/assignmentDisplay.test.js`

Expected: PASS with five tests.

- [ ] **Step 5: Commit the formatter**

```bash
git add frontend/src/utils/assignmentDisplay.js frontend/src/utils/assignmentDisplay.test.js
git commit -m "fix: format current assignment labels"
```

### Task 2: Shared header displays normalized assignments

**Files:**
- Modify: `frontend/src/components/UserDropdown.vue`
- Test: `frontend/src/components/UserDropdown.test.js`

**Interfaces:**
- Consumes: `currentAssignmentLabel` from Task 1, `portalStore.assignments`, `portalStore.isLoaded`, and `userStore.userInfo.assignment_summaries`.
- Produces: the existing `roleLabel` computed value, now backed by current assignments.

- [ ] **Step 1: Add a failing component test for the production scenario**

```js
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'

it('shows every current normalized assignment instead of the legacy unassigned role', () => {
  const userStore = useUserStore()
  const portalStore = usePortalStore()
  userStore.setUserInfo({
    full_name: '徐璐',
    role: 'unassigned',
    role_label: '未配置岗位',
    is_superuser: false,
    assignment_summaries: []
  })
  portalStore.permissions = {
    is_superuser: false,
    assignments: [
      { organization_name: '法务风控部', position_name: '部门副总监' },
      { organization_name: '资产财务部', position_name: '财务复核' }
    ],
    permissions: [],
    resources: [],
    company_roles: {}
  }
  portalStore.isLoaded = true

  const wrapper = shallowMount(UserDropdown)
  expect(wrapper.get('.user-role').text()).toBe(
    '法务风控部 / 部门副总监、资产财务部 / 财务复核'
  )
})
```

- [ ] **Step 2: Run the header test and verify the old label fails**

Run: `cd frontend && npm test -- src/components/UserDropdown.test.js`

Expected: FAIL because the rendered tag contains `未配置岗位`.

- [ ] **Step 3: Connect `UserDropdown` to the shared formatter**

```js
import { usePortalStore } from '@/store/portal'
import { currentAssignmentLabel } from '@/utils/assignmentDisplay'

const portalStore = usePortalStore()
const roleLabel = computed(() => currentAssignmentLabel({
  portalAssignments: portalStore.assignments,
  portalLoaded: portalStore.isLoaded,
  userAssignments: userStore.userInfo?.assignment_summaries || [],
  isSuperuser: Boolean(userStore.userInfo?.is_superuser || portalStore.isSuperuser),
  superuserLabel: userStore.roleLabel || toRoleLabel(userStore.role)
}))
```

Keep `signatureDisabled` based on `ROLES.INFO_MAINTAINER`; display text must not alter authorization.

- [ ] **Step 4: Run the header and formatter tests**

Run: `cd frontend && npm test -- src/utils/assignmentDisplay.test.js src/components/UserDropdown.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the header integration**

```bash
git add frontend/src/components/UserDropdown.vue frontend/src/components/UserDropdown.test.js
git commit -m "fix: show current assignments in user header"
```

### Task 3: Profile displays the same assignment label

**Files:**
- Modify: `frontend/src/views/profile/index.vue`
- Create: `frontend/src/views/profile/index.test.js`

**Interfaces:**
- Consumes: the same `currentAssignmentLabel` function and Pinia stores as Task 2.
- Produces: `assignmentLabel: ComputedRef<string>` rendered under the label `当前任职`.

- [ ] **Step 1: Write a failing profile test**

```js
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePortalStore } from '@/store/portal'
import * as userApi from '@/api/user'
import ProfileView from './index.vue'

vi.mock('@/api/user')

describe('profile current assignment', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('uses the same current assignment label as the shared header', async () => {
    userApi.getMe.mockResolvedValue({
      full_name: '徐璐', username: 'xulu', role: 'unassigned',
      role_label: '未配置岗位', is_superuser: false,
      assignment_summaries: []
    })
    const portalStore = usePortalStore()
    portalStore.permissions = {
      is_superuser: false,
      assignments: [{ organization_name: '法务风控部', position_name: '部门副总监' }],
      permissions: [], resources: [], company_roles: {}
    }
    portalStore.isLoaded = true

    const wrapper = shallowMount(ProfileView)
    await flushPromises()

    expect(wrapper.vm.assignmentLabel).toBe('法务风控部 / 部门副总监')
    expect(wrapper.text()).toContain('当前任职')
    expect(wrapper.text()).not.toContain('未配置岗位')
  })
})
```

- [ ] **Step 2: Run the profile test and verify it fails**

Run: `cd frontend && npm test -- src/views/profile/index.test.js`

Expected: FAIL because `assignmentLabel` is absent and the template still renders `role_label`.

- [ ] **Step 3: Replace the legacy role display in the profile**

Change the template field from:

```vue
<el-descriptions-item label="角色">
  <el-tag type="warning" size="small">{{ info?.role_label }}</el-tag>
</el-descriptions-item>
```

to:

```vue
<el-descriptions-item label="当前任职">
  <el-tag type="warning" size="small">{{ assignmentLabel }}</el-tag>
</el-descriptions-item>
```

Add the same formatter inputs used by the header:

```js
import { usePortalStore } from '@/store/portal'
import { currentAssignmentLabel } from '@/utils/assignmentDisplay'

const portalStore = usePortalStore()
const assignmentLabel = computed(() => currentAssignmentLabel({
  portalAssignments: portalStore.assignments,
  portalLoaded: portalStore.isLoaded,
  userAssignments: info.value?.assignment_summaries || [],
  isSuperuser: Boolean(info.value?.is_superuser || portalStore.isSuperuser),
  superuserLabel: info.value?.role_label || '信息维护'
}))
```

- [ ] **Step 4: Run all focused display tests**

Run: `cd frontend && npm test -- src/utils/assignmentDisplay.test.js src/components/UserDropdown.test.js src/views/profile/index.test.js`

Expected: PASS.

- [ ] **Step 5: Commit the profile integration**

```bash
git add frontend/src/views/profile/index.vue frontend/src/views/profile/index.test.js
git commit -m "fix: show current assignments in profile"
```

### Task 4: Regression verification and production rollout

**Files:**
- Verify: `frontend/src/utils/assignmentDisplay.js`
- Verify: `frontend/src/components/UserDropdown.vue`
- Verify: `frontend/src/views/profile/index.vue`
- Deploy: `frontend/dist/`

**Interfaces:**
- Consumes: the three completed frontend tasks.
- Produces: a tested production frontend whose assignment labels match the existing backend permission snapshot.

- [ ] **Step 1: Run the complete frontend test suite**

Run: `cd frontend && npm test`

Expected: all Vitest files pass with no failed tests.

- [ ] **Step 2: Build the production frontend**

Run: `cd frontend && npm run build`

Expected: Vite exits successfully and writes `frontend/dist/index.html` plus hashed assets.

- [ ] **Step 3: Verify repository hygiene and commit state**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intentional uncommitted release artifacts, if any, remain outside the feature worktree.

- [ ] **Step 4: Push the reviewed commits to `main`**

Run: `git push origin HEAD:main`

Expected: remote `main` advances without force-push.

- [ ] **Step 5: Back up and atomically replace only the production frontend**

Package `frontend/dist`, upload it to a release directory named with the final commit SHA, copy the current `/opt/sd-scm/frontend/dist` into that release's rollback directory, move the new directory into place, run `nginx -t`, and reload Nginx. Do not restart or replace the backend because the fix is frontend-only.

- [ ] **Step 6: Verify production behavior**

Confirm all of the following:

```text
GET http://39.107.52.146/api/v1/health returns code=0 and status=ok
live index.html matches the release index.html
the xulu permission snapshot contains 法务风控部 / 部门副总监
the built header formatter renders 法务风控部 / 部门副总监 instead of 未配置岗位
sd-scm-backend.service and nginx.service remain active
```

- [ ] **Step 7: Record the deployed revision**

Update `/opt/sd-scm/REVISION` and `/opt/sd-scm/RELEASE` to the final commit SHA only after all production checks pass. Preserve the frontend rollback directory and report its path.
