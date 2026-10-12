import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ForecastFactorEditor from './ForecastFactorEditor.vue'
import { downloadForecastFactorTemplate, parseForecastFactors } from '@/api/operation'

vi.mock('@/api/operation', () => ({
  downloadForecastFactorTemplate: vi.fn(),
  parseForecastFactors: vi.fn()
}))

describe('ForecastFactorEditor', () => {
  let wrapper

  afterEach(() => {
    wrapper?.unmount()
    vi.clearAllMocks()
  })

  function mountEditor(modelValue = []) {
    wrapper = mount(ForecastFactorEditor, { props: { modelValue } })
    return wrapper
  }

  it('adds, edits, and removes factors through v-model only', async () => {
    mountEditor()
    await wrapper.get('[data-testid="add-factor"]').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)[0][0].factor_type).toBe('天气')

    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue').at(-1)[0] })
    await wrapper.get('[data-testid="factor-name-0"]').setValue('雨天')
    expect(wrapper.emitted('update:modelValue').at(-1)[0][0].name).toBe('雨天')

    await wrapper.setProps({ modelValue: wrapper.emitted('update:modelValue').at(-1)[0] })
    await wrapper.get('[data-testid="remove-factor-0"]').trigger('click')
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual([])
  })

  it('appends valid imported rows and displays row errors', async () => {
    parseForecastFactors.mockResolvedValue({
      items: [{ start_date: '2026-11-01', end_date: '2026-11-03', factor_type: '天气', name: '雨天', impact_rate: '-0.10' }],
      errors: [{ row_no: 3, message: '日期格式错误' }]
    })
    mountEditor([{ name: '已有因素' }])

    const file = new File(['xlsx'], 'factors.xlsx')
    Object.defineProperty(wrapper.get('[data-testid="factor-file"]').element, 'files', { value: [file] })
    await wrapper.get('[data-testid="factor-file"]').trigger('change')
    await flushPromises()

    expect(parseForecastFactors).toHaveBeenCalledWith(file)
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toHaveLength(2)
    expect(wrapper.text()).toContain('第 3 行：日期格式错误')
  })

  it('downloads the generated template', async () => {
    downloadForecastFactorTemplate.mockResolvedValue(new Blob(['template']))
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:template')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    mountEditor()

    await wrapper.get('[data-testid="download-template"]').trigger('click')
    await flushPromises()

    expect(downloadForecastFactorTemplate).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:template')
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })
})
