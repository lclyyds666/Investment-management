import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CaseEditorView from './CaseEditorView.vue'

const api = vi.hoisted(() => ({
  createCase: vi.fn(),
  getCase: vi.fn(),
  listLegalInitiatorOptions: vi.fn(),
  listLegalUserOptions: vi.fn(),
  updateCase: vi.fn()
}))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn() }))
const portal = vi.hoisted(() => ({
  isSuperuser: false,
  permissionCodes: new Set(),
  hasPermission(code) { return this.isSuperuser || this.permissionCodes.has(code) }
}))
const route = vi.hoisted(() => ({ params: {} }))

vi.mock('@/api/legalRisk', () => api)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ back: vi.fn(), replace: vi.fn() })
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(), ElMessage: messages
}))

function mountCaseEditor() {
  return shallowMount(CaseEditorView, {
    global: { stubs: { ElForm: { template: '<form><slot /></form>' } } }
  })
}

describe('legal case editor initiator ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    portal.isSuperuser = false
    portal.permissionCodes = new Set(['investment.legal.cases.create'])
    route.params = {}
    api.listLegalUserOptions.mockResolvedValue([])
  })

  it('auto-selects one case origin and submits its assignment id', async () => {
    api.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 51, company_code: 'xinhuaproperty', company_name: '山东新华置业有限公司', organization_code: 'xinhuaproperty', organization_name: '山东新华置业有限公司' }
    ])
    api.createCase.mockResolvedValue({ id: 9 })
    const wrapper = mountCaseEditor()
    await flushPromises()
    expect(wrapper.vm.form.initiator_assignment_id).toBe(51)
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }
    await wrapper.vm.save()
    expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({ initiator_assignment_id: 51 }))
    expect(api.createCase.mock.calls[0][0]).not.toHaveProperty('organization_code')
  })

  it('blocks a normal user with no valid initiator assignment', async () => {
    api.listLegalInitiatorOptions.mockResolvedValue([])
    const wrapper = mountCaseEditor()
    await flushPromises()

    await wrapper.vm.save()

    expect(api.createCase).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('当前账号没有有效的案件发起任职')
  })

  it('blocks a normal user when initiator options fail to load', async () => {
    api.listLegalInitiatorOptions.mockRejectedValue(new Error('offline'))
    const wrapper = mountCaseEditor()
    await flushPromises()

    await wrapper.vm.save()

    expect(api.createCase).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('案件发起任职加载失败，请稍后重试')
  })

  it('allows only a superuser to submit a proxy organization code', async () => {
    portal.isSuperuser = true
    api.createCase.mockResolvedValue({ id: 10 })
    const wrapper = mountCaseEditor()
    await flushPromises()
    wrapper.vm.form.organization_code = 'xinhuaproperty'
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.save()

    expect(api.listLegalInitiatorOptions).not.toHaveBeenCalled()
    expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({
      organization_code: 'xinhuaproperty'
    }))
    expect(api.createCase.mock.calls[0][0]).not.toHaveProperty('initiator_assignment_id')
  })

  it('rejects direct create attempts when the snapshot lacks create permission', async () => {
    portal.permissionCodes = new Set(['investment.legal.cases.update'])
    api.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 51, company_code: 'xinhuaproperty', organization_code: 'xinhuaproperty' }
    ])
    const wrapper = mountCaseEditor()
    await flushPromises()
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.save()

    expect(api.createCase).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('权限不足，无法新建案件')
  })

  it('allows update-only snapshots to edit without granting create', async () => {
    route.params = { caseId: '7' }
    portal.permissionCodes = new Set(['investment.legal.cases.update'])
    api.getCase.mockResolvedValue({ id: 7, version: 1, case_name: '原案件' })
    api.updateCase.mockResolvedValue({ id: 7 })
    const wrapper = mountCaseEditor()
    await flushPromises()
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.save()

    expect(api.updateCase).toHaveBeenCalledWith('7', expect.objectContaining({ version: 1 }))
    expect(api.createCase).not.toHaveBeenCalled()
  })
})
