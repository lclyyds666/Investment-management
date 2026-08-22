import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportDialog from './ImportDialog.vue'

const api = vi.hoisted(() => ({
  confirmImport: vi.fn(),
  downloadImportErrors: vi.fn(),
  downloadImportTemplate: vi.fn(),
  getImportBatch: vi.fn(),
  listLegalInitiatorOptions: vi.fn(),
  previewImport: vi.fn()
}))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn() }))
const portal = vi.hoisted(() => ({ isSuperuser: false }))

vi.mock('@/api/legalRisk', () => api)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(), ElMessage: messages
}))

function mountImportDialog() {
  return shallowMount(ImportDialog, {
    global: { stubs: { UploadFilled: true } }
  })
}

function dialogState(wrapper) {
  return wrapper.vm.$.setupState
}

describe('legal case import initiator ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    portal.isSuperuser = false
    api.getImportBatch.mockResolvedValue({ rows: [] })
    api.previewImport.mockResolvedValue({ id: 7, error_rows: 0 })
  })

  it('submits a normal user selected assignment in preview', async () => {
    api.listLegalInitiatorOptions.mockResolvedValue([
      { assignment_id: 51, organization_code: 'xinhuaproperty' }
    ])
    const wrapper = mountImportDialog()
    wrapper.vm.open()
    await flushPromises()
    const state = dialogState(wrapper)
    state.selectFile({ raw: new Blob(['xlsx']) })

    await state.preview()

    const formData = api.previewImport.mock.calls[0][0]
    expect(formData.get('initiator_assignment_id')).toBe('51')
    expect(formData.has('organization_code')).toBe(false)
  })

  it('blocks a normal user with no valid initiator assignment', async () => {
    api.listLegalInitiatorOptions.mockResolvedValue([])
    const wrapper = mountImportDialog()
    wrapper.vm.open()
    await flushPromises()
    const state = dialogState(wrapper)
    state.selectFile({ raw: new Blob(['xlsx']) })

    await state.preview()

    expect(api.previewImport).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('当前账号没有有效的案件发起任职')
  })

  it('blocks a normal user when initiator options fail to load', async () => {
    api.listLegalInitiatorOptions.mockRejectedValue(new Error('offline'))
    const wrapper = mountImportDialog()
    wrapper.vm.open()
    await flushPromises()
    const state = dialogState(wrapper)
    state.selectFile({ raw: new Blob(['xlsx']) })

    await state.preview()

    expect(api.previewImport).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('案件发起任职加载失败，请稍后重试')
  })

  it('allows only a superuser to preview with a proxy organization code', async () => {
    portal.isSuperuser = true
    const wrapper = mountImportDialog()
    wrapper.vm.open()
    await flushPromises()
    const state = dialogState(wrapper)
    state.organizationCode = 'xinhuaproperty'
    state.selectFile({ raw: new Blob(['xlsx']) })

    await state.preview()

    expect(api.listLegalInitiatorOptions).not.toHaveBeenCalled()
    const formData = api.previewImport.mock.calls[0][0]
    expect(formData.get('organization_code')).toBe('xinhuaproperty')
    expect(formData.has('initiator_assignment_id')).toBe(false)
  })
})
