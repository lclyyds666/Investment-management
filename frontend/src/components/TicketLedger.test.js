import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

const ticketApi = vi.hoisted(() => ({
  parseTicketFile: vi.fn(), getTicketLedger: vi.fn(), saveTicketLedger: vi.fn(),
  previewTicketRow: vi.fn(), updateTicketRow: vi.fn(), deleteTicketRow: vi.fn(), fetchTicketLedgerExportBlob: vi.fn(),
  uploadTicketConfirm: vi.fn(), approveTicketConfirm: vi.fn(), deleteTicketConfirm: vi.fn(), fetchTicketConfirmBlob: vi.fn()
}))
const contractApi = vi.hoisted(() => ({ listEligibleContracts: vi.fn() }))

vi.mock('@/api/ticketLedger', () => ticketApi)
vi.mock('@/api/contract', () => contractApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => ({ isSuperuser: true }) }))
vi.mock('@/utils/businessAuthorization', () => ({ canUsePermission: vi.fn(() => true) }))

import TicketLedger from './TicketLedger.vue'

function mountLedger() {
  const passthrough = { template: '<div><slot /><slot name="footer" /></div>' }
  return shallowMount(TicketLedger, {
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

describe('TicketLedger platform editor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ticketApi.getTicketLedger.mockResolvedValue([])
    contractApi.listEligibleContracts.mockResolvedValue([])
  })

  it('offers 票付通 as a user-visible edit option', async () => {
    const wrapper = mountLedger()
    wrapper.vm.openEdit({ platform: '美团' })
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.platform-option').map((option) => option.text())).toEqual([
      '抖音', '美团', '携程', '同程', '票付通'
    ])
  })

  it('defaults confirmation to the remembered ticket contract and submits it', async () => {
    contractApi.listEligibleContracts.mockResolvedValue([
      { id: 11, contract_no: 'T-11', title: '旧门票合同', is_preferred: false },
      { id: 12, contract_no: 'T-12', title: '最近门票合同', is_preferred: true }
    ])
    ticketApi.approveTicketConfirm.mockResolvedValue({})
    const wrapper = mountLedger()
    const period = { period_row_id: 101 }

    await wrapper.vm.openConfirmContract(period)
    expect(contractApi.listEligibleContracts).toHaveBeenLastCalledWith('quancheng-ouleb', 'ticket')
    expect(wrapper.vm.confirmForm.contract_id).toBe(12)

    await wrapper.vm.confirmPeriod()
    expect(ticketApi.approveTicketConfirm).toHaveBeenCalledWith(
      'quancheng-ouleb',
      101,
      { contract_id: 12 }
    )
  })

  it('disables confirmation when no ticket contract is eligible', async () => {
    const wrapper = mountLedger()

    await wrapper.vm.refreshEligibleContracts()

    expect(wrapper.vm.canConfirmWithContract).toBe(false)
  })
})
