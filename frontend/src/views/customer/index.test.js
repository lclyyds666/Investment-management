import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const customerApi = vi.hoisted(() => ({
  listCustomers: vi.fn(),
  getCustomer: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
  listMaterials: vi.fn(),
  uploadMaterials: vi.fn(),
  deleteMaterial: vi.fn(),
  fetchMaterialBlob: vi.fn()
}))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))

vi.mock('@/api/customer', () => customerApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ isSuperuser: true }) }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: () => true }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: messages,
  ElMessageBox: { confirm: vi.fn() }
}))

import CustomerView from './index.vue'

const passthrough = { template: '<div><slot /><slot name="footer" /></div>' }
const labeledItem = {
  props: ['label'],
  template: '<div><span>{{ label }}</span><slot /></div>'
}

function mountView() {
  return shallowMount(CustomerView, {
    global: {
      directives: { loading: () => {} },
      stubs: {
        ProTable: { methods: { reload() {} }, template: '<div />' },
        CustomerResearchDialog: true,
        ElDialog: passthrough,
        ElDrawer: passthrough,
        ElForm: passthrough,
        ElFormItem: labeledItem,
        ElRow: passthrough,
        ElCol: passthrough,
        ElInput: true,
        ElUpload: passthrough,
        ElDescriptions: passthrough,
        ElDescriptionsItem: labeledItem,
        ElButton: passthrough,
        ElTag: passthrough,
        ElIcon: passthrough
      }
    }
  })
}

describe('customer bank fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    customerApi.listCustomers.mockResolvedValue({ items: [], total: 0 })
    customerApi.listMaterials.mockResolvedValue([])
    customerApi.updateCustomer.mockResolvedValue({})
    customerApi.createCustomer.mockResolvedValue({ id: 1 })
  })

  it('initializes an empty create form with both bank fields', () => {
    const wrapper = mountView()

    wrapper.vm.openCreate()

    expect(wrapper.vm.form).toEqual(expect.objectContaining({
      bank_name: '',
      bank_account: ''
    }))
    expect(wrapper.text()).toContain('开户行')
    expect(wrapper.text()).toContain('账号')
  })

  it('loads both bank fields when editing a customer', async () => {
    customerApi.getCustomer.mockResolvedValue({
      id: 7,
      customer_code: 'KH-007',
      name: '测试客户',
      bank_name: '中国银行济南分行',
      bank_account: '6217000012345678'
    })
    const wrapper = mountView()

    await wrapper.vm.openEdit({ id: 7, customer_code: 'KH-007', name: '测试客户' })

    expect(wrapper.vm.form.bank_name).toBe('中国银行济南分行')
    expect(wrapper.vm.form.bank_account).toBe('6217000012345678')
  })

  it('includes both bank fields in the edit payload', async () => {
    customerApi.getCustomer.mockResolvedValue({
      id: 8,
      customer_code: 'KH-008',
      name: '保存客户',
      bank_name: '原开户行',
      bank_account: '10001'
    })
    const wrapper = mountView()
    await wrapper.vm.openEdit({ id: 8, customer_code: 'KH-008', name: '保存客户' })
    Object.assign(wrapper.vm.form, {
      bank_name: '招商银行济南分行',
      bank_account: '6225888899990000'
    })
    wrapper.vm.formRef = { validate: vi.fn().mockResolvedValue(true) }

    await wrapper.vm.onSave()

    expect(customerApi.updateCustomer).toHaveBeenCalledWith(8, expect.objectContaining({
      bank_name: '招商银行济南分行',
      bank_account: '6225888899990000'
    }))
  })

  it('displays both bank fields in customer details', async () => {
    const wrapper = mountView()

    await wrapper.vm.openView({
      id: 9,
      customer_code: 'KH-009',
      name: '详情客户',
      bank_name: '工商银行青岛分行',
      bank_account: '9558800011223344'
    })
    await flushPromises()

    expect(wrapper.text()).toContain('开户行')
    expect(wrapper.text()).toContain('工商银行青岛分行')
    expect(wrapper.text()).toContain('账号')
    expect(wrapper.text()).toContain('9558800011223344')
  })
})
