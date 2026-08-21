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

vi.mock('@/api/legalRisk', () => api)
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ back: vi.fn(), replace: vi.fn() })
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(), ElMessage: { success: vi.fn(), warning: vi.fn() }
}))

function mountCaseEditor() {
  return shallowMount(CaseEditorView, {
    global: { stubs: { ElForm: { template: '<form><slot /></form>' } } }
  })
}

describe('legal case editor initiator ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
})
