import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const scenicApi = vi.hoisted(() => ({
  getScenicConfigs: vi.fn(),
  updateScenicConfig: vi.fn(),
  updateHotelScenicConfig: vi.fn()
}))
const portal = vi.hoisted(() => ({ isSuperuser: true }))
const authorization = vi.hoisted(() => ({ canUsePermission: vi.fn(() => true) }))
const messages = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn() }))

vi.mock('@/api/scenic', () => scenicApi)
vi.mock('@/store/portal', () => ({ usePortalStore: () => portal }))
vi.mock('@/utils/businessAuthorization', () => authorization)
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal(),
  ElMessage: messages
}))

import ScenicConfigDialog from './ScenicConfigDialog.vue'

const config = {
  scenic_id: 'quanzhou',
  scenic_name: '泉州欧乐堡',
  default_ticket_product: '欢乐门票',
  ticket_rate_hexiao: 0.9,
  ticket_rate_settle: 0.94,
  ticket_commission_rate: 0.06,
  ticket_default_commission: 100,
  default_hotel_name: '郑和海洋酒店',
  hotel_rate_hexiao: 0.91,
  hotel_rate_settle: 0.95,
  hotel_commission_rate: 0.08,
  hotel_fee_per_night: 58,
  hotel_fee_algo: 2,
  hotel_platforms: ['抖音', '美团', '携程', '票付通']
}

const canonicalScenics = [
  ['quancheng-ouleb', '泉城欧乐堡'],
  ['quanzhou-ouleb', '泉州欧乐堡'],
  ['fuzhou-ouleb', '福州欧乐堡'],
  ['zunyi-zoo', '遵义动物园'],
  ['nanyang-wildlife', '南阳森林野生动物世界'],
  ['guanquelou', '鹳雀楼'],
  ['changsha-dongqu', '长沙动趣王国']
]
const configsForAllScenics = canonicalScenics.map(([scenic_id, scenic_name]) => ({
  ...config,
  scenic_id,
  scenic_name
}))

const passthrough = { template: '<div><slot /><slot name="footer" /></div>' }
const table = { template: '<div><slot /><slot name="empty" /></div>' }
const tableColumn = {
  data: () => ({ row: { hotel_platforms: [] } }),
  template: '<div><slot :row="row" /></div>'
}
const global = {
  stubs: {
    ElDialog: passthrough,
    ElTabs: passthrough,
    ElTabPane: { props: ['label'], template: '<section>{{ label }}<slot /></section>' },
    ElTable: table,
    ElTableColumn: tableColumn,
    ElInput: true,
    ElInputNumber: true,
    ElSelect: true,
    ElOption: { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
    ElRadioGroup: passthrough,
    ElRadio: { props: ['label'], template: '<label><slot /></label>' },
    ElCheckboxGroup: passthrough,
    ElCheckbox: { props: ['label'], template: '<label>{{ label }}<slot /></label>' },
    ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' }
  }
}

describe('ScenicConfigDialog hotel configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    scenicApi.getScenicConfigs.mockResolvedValue([config])
    scenicApi.updateHotelScenicConfig.mockResolvedValue(config)
  })

  it('renders independent ticket and hotel configuration tabs with canonical platforms', async () => {
    const wrapper = shallowMount(ScenicConfigDialog, { global })
    await wrapper.vm.loadConfigs()

    expect(wrapper.text()).toContain('门票配置')
    expect(wrapper.text()).toContain('酒店配置')
    expect(wrapper.text()).toContain('票付通')
    expect(wrapper.vm.rows[0].hotel_platforms).toEqual(['抖音', '美团', '携程', '票付通'])
  })

  it('saves the hotel fields using the Task 5 API contract', async () => {
    const wrapper = shallowMount(ScenicConfigDialog, { global })
    await wrapper.vm.loadConfigs()

    await wrapper.vm.saveHotelRow(wrapper.vm.rows[0])

    expect(scenicApi.updateHotelScenicConfig).toHaveBeenCalledWith('quanzhou', {
      default_hotel_name: '郑和海洋酒店',
      hotel_rate_hexiao: 0.91,
      hotel_rate_settle: 0.95,
      hotel_commission_rate: 0.08,
      hotel_fee_per_night: 58,
      hotel_fee_algo: 2,
      hotel_platforms: ['抖音', '美团', '携程', '票付通']
    })
  })

  it('shows hotel configuration only for hotel-enabled scenic spots', async () => {
    scenicApi.getScenicConfigs.mockResolvedValue(configsForAllScenics)
    const wrapper = shallowMount(ScenicConfigDialog, { global })
    await wrapper.vm.loadConfigs()

    expect(wrapper.vm.rows.map((row) => row.scenic_id)).toEqual([
      'quancheng-ouleb', 'quanzhou-ouleb', 'fuzhou-ouleb',
      'zunyi-zoo', 'nanyang-wildlife', 'guanquelou', 'changsha-dongqu'
    ])
    expect(wrapper.vm.hotelRows.map((row) => row.scenic_id)).toEqual([
      'quancheng-ouleb', 'quanzhou-ouleb', 'fuzhou-ouleb'
    ])
  })
})
