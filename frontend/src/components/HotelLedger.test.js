import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

const hotelApi = vi.hoisted(() => ({
  parseHotelFile: vi.fn(), getHotelLedger: vi.fn(), saveHotelLedger: vi.fn(),
  previewHotelRow: vi.fn(), updateHotelRow: vi.fn(), deleteHotelRow: vi.fn(), fetchHotelLedgerExportBlob: vi.fn(),
  uploadHotelConfirm: vi.fn(), approveHotelConfirm: vi.fn(), deleteHotelConfirm: vi.fn(), fetchHotelConfirmBlob: vi.fn()
}))

vi.mock('@/api/hotelLedger', () => hotelApi)
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
  })

  it('offers 票付通 as a user-visible edit option', async () => {
    const wrapper = mountLedger()
    wrapper.vm.openEdit({ platform: '美团' })
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.platform-option').map((option) => option.text())).toEqual([
      '抖音', '美团', '携程', '票付通'
    ])
  })
})
