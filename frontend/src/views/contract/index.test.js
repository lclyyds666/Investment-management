import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const contractApi = vi.hoisted(() => ({
  listContracts: vi.fn(), createContract: vi.fn(), updateContract: vi.fn(), deleteContract: vi.fn(), submitContract: vi.fn(),
  uploadContractAttachment: vi.fn(), approveContract: vi.fn(), rejectContract: vi.fn(), aiReviewContract: vi.fn(), exportContracts: vi.fn(), fetchContractAttachmentBlob: vi.fn()
}))
const workflowApi = vi.hoisted(() => ({ listWorkflowCandidates: vi.fn(() => Promise.resolve([])), getWorkflowSubmissionPlan: vi.fn(), getWorkflowTimeline: vi.fn() }))
const legalApi = vi.hoisted(() => ({ listLegalInitiatorOptions: vi.fn(() => Promise.resolve([])) }))
const badgeStore = vi.hoisted(() => ({ refresh: vi.fn() }))
const portal = vi.hoisted(() => ({
  isSuperuser: false,
  permissionCodes: new Set([
    'investment.legal.contracts.view',
    'investment.legal.contracts.create',
    'investment.legal.contracts.update',
    'investment.legal.contracts.delete',
    'investment.legal.contracts.submit',
    'investment.legal.contracts.export'
  ])
}))
const authorization = vi.hoisted(() => ({
  canUsePermission: vi.fn((store, code) => store.isSuperuser || store.permissionCodes.has(code))
}))
const fileApi = vi.hoisted(() => ({ downloadBlob: vi.fn(), previewBlob: vi.fn() }))
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/api/customer', () => ({ listCustomers: vi.fn(() => Promise.resolve([])) }))
vi.mock('@/api/knowledge', () => ({ listKnowledge: vi.fn(), uploadKnowledge: vi.fn(), deleteKnowledge: vi.fn() }))
vi.mock('@/api/workflow', () => workflowApi)
vi.mock('@/api/legalRisk', () => legalApi)
vi.mock('@/components/workflow/DesignatedApproverFields.vue', () => ({
  default: {
    props: ['workflowCode', 'nodes', 'targetType', 'targetId'],
    async mounted() { await workflowApi.listWorkflowCandidates(this.workflowCode, 'company_leader', this.targetType, this.targetId) },
    template: '<div data-testid="selector-stub" />'
  }
}))
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('@/store/user', () => ({ useUserStore: () => ({ userInfo: { id: 99 } }) }))
vi.mock('@/store/approvalBadge', () => ({ useApprovalBadgeStore: () => badgeStore }))
vi.mock('@/utils/businessAuthorization', () => authorization)
vi.mock('@/utils/file', () => fileApi)
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({ ...await importOriginal(), ElMessage: messages, ElMessageBox: { confirm: vi.fn() } }))

import ContractView from './index.vue'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mountView() {
  return shallowMount(ContractView, {
    global: {
      stubs: {
        ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
        ElCard: { template: '<div><slot name="header" /><slot /></div>' },
        ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
        DesignatedApproverFields: false
      }
    }
  })
}

describe('contract designated submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
    contractApi.submitContract.mockResolvedValue({})
    contractApi.exportContracts.mockResolvedValue(new Blob(['csv']))
    portal.isSuperuser = false
    legalApi.listLegalInitiatorOptions.mockResolvedValue([])
    workflowApi.getWorkflowSubmissionPlan.mockResolvedValue({ nodes: [] })
  })

  it('requires an initiator assignment when several legal origins are available', async () => {
    legalApi.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 11, organization_code: 'investment.general', organization_name: '综合管理部', company_code: 'investment' },
      { assignment_id: 12, organization_code: 'supplymanagement', organization_name: '山东出版供应链管理有限公司', company_code: 'supplymanagement' }
    ])
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openCreate()
    expect(wrapper.vm.form.initiator_assignment_id).toBeNull()
    expect(wrapper.vm.rules.initiator_assignment_id[0].required).toBe(true)
  })

  it('keeps contract creation disabled while origins load and when none are available', async () => {
    const optionsRequest = deferred()
    legalApi.listLegalInitiatorOptions.mockReturnValue(optionsRequest.promise)
    const wrapper = mountView()

    expect(wrapper.vm.canOpenCreate).toBe(false)
    expect(wrapper.find('[data-testid="create-contract"]').attributes('disabled')).toBeDefined()
    wrapper.vm.openCreate()
    expect(wrapper.vm.dialogVisible).toBe(false)

    optionsRequest.resolve([])
    await flushPromises()
    expect(wrapper.vm.canOpenCreate).toBe(false)
    expect(wrapper.find('[data-testid="create-contract"]').attributes('disabled')).toBeDefined()
    wrapper.vm.openCreate()
    expect(wrapper.vm.dialogVisible).toBe(false)

    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.onSave()
    expect(contractApi.createContract).not.toHaveBeenCalled()
  })

  it('creates a contract when a legal origin is available', async () => {
    legalApi.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 12, organization_code: 'supplymanagement', organization_name: '山东出版供应链管理有限公司', company_code: 'supplymanagement' }
    ])
    contractApi.createContract.mockResolvedValue({ id: 81 })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-testid="create-contract"]').attributes('disabled')).toBeUndefined()
    wrapper.vm.openCreate()
    expect(wrapper.vm.dialogVisible).toBe(true)
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.onSave()

    expect(contractApi.createContract).toHaveBeenCalledWith(expect.objectContaining({ initiator_assignment_id: 12 }))
  })

  it('lets a superuser select a real contract organization without a fake assignment', async () => {
    portal.isSuperuser = true
    legalApi.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: null, organization_code: 'supplymanagement', organization_name: '山东出版供应链管理有限公司', company_code: 'supplymanagement' }
    ])
    contractApi.createContract.mockResolvedValue({ id: 82 })
    const wrapper = mountView()
    await flushPromises()

    wrapper.vm.openCreate()
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.onSave()

    expect(contractApi.createContract).toHaveBeenCalledWith(expect.objectContaining({
      organization_code: 'supplymanagement'
    }))
    expect(contractApi.createContract.mock.calls[0][0]).not.toHaveProperty('initiator_assignment_id')
  })

  it('uses only the official legal-contract permission family for page actions', async () => {
    const wrapper = mountView()
    await flushPromises()

    const pageActions = [
      wrapper.vm.canCreate,
      wrapper.vm.canUpdate,
      wrapper.vm.canDelete,
      wrapper.vm.canSubmit,
      wrapper.vm.canExport,
      wrapper.vm.canViewKnowledge,
      wrapper.vm.canManageKnowledge
    ]
    pageActions.forEach((allowed) => expect(allowed).toBe(true))
    const requested = authorization.canUsePermission.mock.calls.map(([, code]) => code)
    expect(requested).toEqual(expect.arrayContaining([
      'investment.legal.contracts.create',
      'investment.legal.contracts.update',
      'investment.legal.contracts.delete',
      'investment.legal.contracts.submit',
      'investment.legal.contracts.export',
      'investment.legal.contracts.view'
    ]))
    expect(requested.some((code) => code.startsWith('supply.contract.'))).toBe(false)
  })

  it('downloads the server-scoped contract export once', async () => {
    const blob = new Blob(['server csv'])
    contractApi.exportContracts.mockResolvedValue(blob)
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-testid="export-contract-ledger"]').exists()).toBe(true)
    await wrapper.vm.exportLedger()

    expect(contractApi.exportContracts).toHaveBeenCalledTimes(1)
    expect(fileApi.downloadBlob).toHaveBeenCalledWith(
      blob,
      expect.stringMatching(/^合同台账_\d{4}-\d{2}-\d{2}\.csv$/)
    )
    expect(messages.success).toHaveBeenCalledWith('合同台账导出成功')
  })

  it('defaults party A to the Zhanwei company name when the option omits company_name', async () => {
    legalApi.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 14, organization_code: 'zhanwei', organization_name: '山东展威科技有限公司', company_code: 'zhanwei' }
    ])
    const wrapper = mountView()
    await flushPromises()

    wrapper.vm.openCreate()
    expect(wrapper.vm.form.initiator_assignment_id).toBe(14)
    expect(wrapper.vm.form.party_a).toBe('山东展威科技有限公司')
  })

  it('loads the server submission plan before opening the designated chain', async () => {
    workflowApi.getWorkflowSubmissionPlan.mockResolvedValue({
      workflow_code: 'investment.contract.department.v1',
      workflow_name: '投资公司部门合同审批',
      organization_name: '综合管理部',
      nodes: [
        { code: 'department_head', name: '经办部门负责人', position_name: '部门主任' },
        { code: 'chairman', name: '单位主要负责人', position_name: '董事长' }
      ]
    })
    const wrapper = mountView()
    await wrapper.vm.onSubmit({ id: 7, status: 'draft', workflow_instance_id: null })
    expect(workflowApi.getWorkflowSubmissionPlan).toHaveBeenCalledWith('contract', 7)
    expect(wrapper.vm.submitVisible).toBe(true)
    expect(wrapper.vm.submitNodes.map(node => node.name)).toEqual(['经办部门负责人', '单位主要负责人'])
  })

  it('discards a late submission plan from an earlier contract', async () => {
    const firstPlan = deferred()
    const secondPlan = deferred()
    workflowApi.getWorkflowSubmissionPlan
      .mockReturnValueOnce(firstPlan.promise)
      .mockReturnValueOnce(secondPlan.promise)
    const wrapper = mountView()
    const firstSubmit = wrapper.vm.onSubmit({ id: 21, status: 'draft', workflow_instance_id: null })
    const secondSubmit = wrapper.vm.onSubmit({ id: 22, status: 'draft', workflow_instance_id: null })

    secondPlan.resolve({ workflow_code: 'workflow.second', nodes: [{ code: 'second', name: '第二合同节点', position_name: '负责人' }] })
    await secondSubmit
    expect(wrapper.vm.submitCurrent.id).toBe(22)
    expect(wrapper.vm.submitPlan.workflow_code).toBe('workflow.second')
    expect(wrapper.vm.submitVisible).toBe(true)

    firstPlan.resolve({ workflow_code: 'workflow.first', nodes: [{ code: 'first', name: '第一合同节点', position_name: '负责人' }] })
    await firstSubmit
    expect(wrapper.vm.submitCurrent.id).toBe(22)
    expect(wrapper.vm.submitPlan.workflow_code).toBe('workflow.second')
    expect(wrapper.vm.submitNodes.map((node) => node.code)).toEqual(['second'])
  })

  it('blocks first submission until the selector validates and sends designated users', async () => {
    const wrapper = mountView()
    await flushPromises()
    const row = { id: 7, status: 'draft', workflow_instance_id: null }
    await wrapper.vm.onSubmit(row)
    expect(contractApi.submitContract).not.toHaveBeenCalled()

    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(false) }
    await wrapper.vm.confirmSubmit()
    expect(contractApi.submitContract).not.toHaveBeenCalled()

    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmSubmit()
    expect(contractApi.submitContract).toHaveBeenCalledWith(7, { designated_users: { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 } })
  })

  it('resubmits an active handler task without forcing approver reselection', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 8, status: 'rejected', workflow_instance_id: 44, active_task: { node_code: 'handler' } })
    expect(contractApi.submitContract).toHaveBeenCalledWith(8, undefined)
  })

  it('reloads candidates after an eligibility conflict and preserves the dialog', async () => {
    contractApi.submitContract.mockRejectedValueOnce({ response: { status: 422 } })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 9, status: 'draft', workflow_instance_id: null })
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true), reloadCandidates: vi.fn().mockResolvedValue(true) }
    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }

    await wrapper.vm.confirmSubmit()

    expect(wrapper.vm.submitVisible).toBe(true)
  })

  it('only mounts the candidate selector while open and reloads it when reopened', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).not.toHaveBeenCalled()

    await wrapper.vm.onSubmit({ id: 11, status: 'draft', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(1)

    wrapper.vm.submitVisible = false
    await wrapper.vm.$nextTick()
    await wrapper.vm.onSubmit({ id: 11, status: 'draft', workflow_instance_id: null })
    await flushPromises()
    expect(workflowApi.listWorkflowCandidates).toHaveBeenCalledTimes(2)
  })

  it('sends one request when confirm is invoked concurrently', async () => {
    let resolveSubmit
    contractApi.submitContract.mockImplementationOnce(() => new Promise((resolve) => { resolveSubmit = resolve }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.vm.onSubmit({ id: 12, status: 'draft', workflow_instance_id: null })
    wrapper.vm.selectedApprovers = { company_leader: 11, legal_counsel: 21, supply_governance_leader: 31 }
    wrapper.vm.submitFieldsRef = { validate: vi.fn().mockResolvedValue(true) }

    const first = wrapper.vm.confirmSubmit()
    const second = wrapper.vm.confirmSubmit()
    await flushPromises()
    expect(contractApi.submitContract).toHaveBeenCalledTimes(1)
    resolveSubmit({})
    await Promise.all([first, second])
  })
})

describe('contract active-task actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
  })

  it('shows actions only from active_task and can_act, including shared and designated tasks', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.vm.canApprove({ active_task: { mode: 'shared_position' }, can_act: true })).toBe(true)
    expect(wrapper.vm.canApprove({ active_task: { mode: 'designated_user', designated_user: { full_name: '指定领导' } }, can_act: false })).toBe(false)
    expect(wrapper.vm.canApprove({ active_task: { mode: 'designated_user', designated_user: { full_name: '指定领导' } }, can_act: true })).toBe(true)
    expect(wrapper.vm.canApprove({ active_task: null, can_act: true })).toBe(false)
  })

  it('closes and refreshes after a completed-task conflict', async () => {
    contractApi.approveContract.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'task_already_completed', actor: '王审批' } } } })
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openAction({ id: 7, active_task: { id: 71 }, can_act: true }, 'approve')
    wrapper.vm.actionFormRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.confirmAction()
    expect(wrapper.vm.actionVisible).toBe(false)
    expect(contractApi.listContracts).toHaveBeenCalledTimes(2)
    expect(messages.warning).toHaveBeenCalledWith('该节点已由 王审批 办理')
  })

  it('sends one action request when validation is still pending', async () => {
    const validation = deferred()
    contractApi.approveContract.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.openAction({ id: 8, active_task: { id: 81 }, can_act: true }, 'approve')
    const validate = vi.fn(() => validation.promise)
    wrapper.vm.actionFormRef = { validate }

    const first = wrapper.vm.confirmAction()
    const second = wrapper.vm.confirmAction()
    validation.resolve(true)
    await Promise.all([first, second])

    expect(validate).toHaveBeenCalledTimes(1)
    expect(contractApi.approveContract).toHaveBeenCalledTimes(1)
  })
})

describe('contract AI review output', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    contractApi.listContracts.mockResolvedValue([])
  })

  it('renders AI markdown without executable or link markup', async () => {
    const wrapper = mountView()
    await flushPromises()
    wrapper.vm.aiResult = {
      markdown: '**风险提示** <img src=x onerror=alert(1)> [恶意链接](https://evil.example)'
    }
    await wrapper.vm.$nextTick()

    const html = wrapper.find('.md-body').html()
    expect(html).toContain('风险提示')
    expect(html).toContain('<strong>风险提示</strong>')
    expect(html).not.toMatch(/<img|onerror|href=/i)
  })
})
