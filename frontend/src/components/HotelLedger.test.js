import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

const hotelApi = vi.hoisted(() => ({
  parseHotelFile: vi.fn(), getHotelLedger: vi.fn(), saveHotelLedger: vi.fn(),
  previewHotelRow: vi.fn(), updateHotelRow: vi.fn(), deleteHotelRow: vi.fn(), fetchHotelLedgerExportBlob: vi.fn(),
  uploadHotelConfirm: vi.fn(), approveHotelConfirm: vi.fn(), deleteHotelConfirm: vi.fn(), fetchHotelConfirmBlob: vi.fn()
}))
const contractApi = vi.hoisted(() => ({ listEligibleContracts: vi.fn() }))

vi.mock('@/api/hotelLedger', () => hotelApi)
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ isSuperuser: true }) }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: vi.fn(() => true) }))

import HotelLedger from './HotelLedger.vue'

function mountLedger() {
  const passthrough = { template: '<div><slot /><slot name="footer" /></div>' }
  return shallowMount(HotelLedger, {
    props: { scenicId: 'quancheng-ouleb' },
    global: {
      stubs: {
        ElDialog: passthrough,
        ElForm: passthrough,
        ElFormItem: passthrough,
        ElSelect: passthrough,
        ElOption: { props: ['label'], template: '<span class="platform-option">{{ label }}</span>' }
      }
    }
  })
}

describe('HotelLedger platform editor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hotelApi.getHotelLedger.mockResolvedValue([])
    contractApi.listEligibleContracts.mockResolvedValue([])
  })

  it('offers 票付通 as a user-visible edit option', async () => {
    const wrapper = mountLedger()
    wrapper.vm.openEdit({ platform: '美团' })
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.platform-option').map((option) => option.text())).toEqual([
      '抖音', '美团', '携程', '票付通'
    ])
  })

  it('defaults confirmation to the remembered hotel contract and submits it', async () => {
    contractApi.listEligibleContracts.mockResolvedValue([
      { id: 21, contract_no: 'H-21', title: '旧酒店合同', is_preferred: false },
      { id: 22, contract_no: 'H-22', title: '最近酒店合同', is_preferred: true }
    ])
    hotelApi.approveHotelConfirm.mockResolvedValue({})
    const wrapper = mountLedger()
    const period = { period_row_id: 202 }

    await wrapper.vm.openConfirmContract(period)
    expect(contractApi.listEligibleContracts).toHaveBeenLastCalledWith('quancheng-ouleb', 'hotel')
    expect(wrapper.vm.confirmForm.contract_id).toBe(22)

    await wrapper.vm.confirmPeriod()
    expect(hotelApi.approveHotelConfirm).toHaveBeenCalledWith(
      'quancheng-ouleb',
      202,
      { contract_id: 22 }
    )
  })

  it('disables confirmation when no hotel contract is eligible', async () => {
    const wrapper = mountLedger()

    await wrapper.vm.refreshEligibleContracts()

    expect(wrapper.vm.canConfirmWithContract).toBe(false)
  })
})
