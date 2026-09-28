import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

const ticketApi = vi.hoisted(() => ({
  parseTicketFile: vi.fn(), getTicketLedger: vi.fn(), saveTicketLedger: vi.fn(),
  previewTicketRow: vi.fn(), updateTicketRow: vi.fn(), deleteTicketRow: vi.fn(), fetchTicketLedgerExportBlob: vi.fn(),
  uploadTicketConfirm: vi.fn(), approveTicketConfirm: vi.fn(), deleteTicketConfirm: vi.fn(), fetchTicketConfirmBlob: vi.fn()
}))

vi.mock('@/api/ticketLedger', () => ticketApi)
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
  })

  it('offers 票付通 as a user-visible edit option', async () => {
    const wrapper = mountLedger()
    wrapper.vm.openEdit({ platform: '美团' })
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.platform-option').map((option) => option.text())).toEqual([
      '抖音', '美团', '携程', '同程', '票付通'
    ])
  })
})
