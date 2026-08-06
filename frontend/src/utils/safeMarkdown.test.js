import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DOMPurify from 'dompurify'
import MessageBubble from '@/components/ai/MessageBubble.vue'
import { renderSafeMarkdown, validatedAction } from './safeMarkdown'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

describe('safe AI output', () => {
  it('removes scripts, event handlers, images, media, and links', () => {
    const html = renderSafeMarkdown([
      '[外链](https://evil.example)',
      '<img src=x onerror=alert(1)>',
      '<script>alert(1)</script>',
      '<video src="https://evil.example/a.mp4"></video>',
      '<svg onload="alert(1)"></svg>'
    ].join(''))

    expect(html).not.toMatch(/script|onerror|onload|<img|<video|<svg|href=|src=/i)
    expect(html).toContain('外链')
  })

  it('removes URL text and fails closed when DOMPurify is unavailable', () => {
    const html = renderSafeMarkdown([
      '访问 https://evil.example/a 或 www.evil.example，不应展示目标。',
      '',
      '`ftp://evil.example/file` 与 mailto:test@evil.example',
      '',
      '实体编码 https&#58;//evil.example/path',
      '',
      'IPv6 http://[::1]/health，Unicode https://例子.测试/路径，正文保留。'
    ].join('\n'))
    expect(html).not.toMatch(/https?:\/\/|ftp:\/\/|www\.|mailto:/i)
    expect(html).toContain('不应展示目标')
    expect(html).toContain('正文保留')

    const originalSupport = DOMPurify.isSupported
    DOMPurify.isSupported = false
    try {
      expect(renderSafeMarkdown('**不会降级为原始 HTML**')).toBe('')
    } finally {
      DOMPurify.isSupported = originalSupport
    }
  })

  it('keeps only the approved text and table structure without attributes', () => {
    const html = renderSafeMarkdown('# **重点**\n\n- [x] 已核对\n\n| 景区 | 金额 |\n| :---: | ---: |\n| 遵义 | `120` |\n\n<span style="color:red" data-x="1">说明</span>')

    expect(html).toContain('<strong>重点</strong>')
    expect(html).toContain('<table>')
    expect(html).toContain('<code>120</code>')
    expect(html).not.toMatch(/style=|data-x=|align=|class=|<span|<input|<h1/i)
  })

  it('accepts only exact scenic navigation actions', () => {
    expect(validatedAction({
      type: 'navigate_to_scenic',
      scenic_id: 'zunyi-zoo',
      label: ' 前往遵义动物园 '
    })).toEqual({
      type: 'navigate_to_scenic',
      scenic_id: 'zunyi-zoo',
      label: '前往遵义动物园'
    })
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往', url: 'https://evil.example' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'custom-museum-2026', label: '前往' })).toEqual({
      type: 'navigate_to_scenic', scenic_id: 'custom-museum-2026', label: '前往'
    })
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: '../admin', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'ZUNYI', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'custom_name', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'https://evil.example', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: '-unsafe-', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'open_url', scenic_id: 'zunyi-zoo', label: '前往' })).toBeNull()
    expect(validatedAction({ type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: ' '.repeat(81) })).toBeNull()

    const inherited = Object.assign(Object.create({ url: 'https://evil.example' }), {
      type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往'
    })
    expect(validatedAction(inherited)).toBeNull()

    const hiddenExtra = { type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往' }
    Object.defineProperty(hiddenExtra, 'url', { value: 'https://evil.example' })
    expect(validatedAction(hiddenExtra)).toBeNull()

    let getterCalls = 0
    const accessor = { type: 'navigate_to_scenic', label: '前往' }
    Object.defineProperty(accessor, 'scenic_id', {
      enumerable: true,
      get() {
        getterCalls += 1
        return 'zunyi-zoo'
      }
    })
    expect(validatedAction(accessor)).toBeNull()
    expect(getterCalls).toBe(0)

    const proxied = new Proxy({
      type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往'
    }, {})
    expect(validatedAction(proxied)).toBeNull()
  })

  it('navigates through the fixed named route only after a valid action click', async () => {
    push.mockClear()
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          role: 'assistant',
          content: '可查看对应景区。',
          status: 'completed',
          actions_json: [
            { type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '前往遵义动物园' },
            { type: 'navigate_to_scenic', scenic_id: 'nanyang-world', label: '危险', url: '/admin' }
          ]
        }
      },
      global: {
        stubs: {
          ElButton: {
            props: ['ariaLabel'],
            emits: ['click'],
            template: '<button :aria-label="ariaLabel" @click="$emit(\'click\')"><slot /></button>'
          },
          ElIcon: true
        }
      }
    })

    expect(push).not.toHaveBeenCalled()
    expect(wrapper.findAll('button')).toHaveLength(1)
    await wrapper.get('button').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'CulturalTourismDetail',
      params: { scenicId: 'zunyi-zoo' }
    })
  })

  it('treats malformed action collections as no actions', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          role: 'assistant',
          content: '无操作',
          status: 'completed',
          actions_json: { type: 'navigate_to_scenic' }
        }
      },
      global: { stubs: { ElButton: true, ElIcon: true } }
    })

    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('does not trust a native proxy that spoofs Vue reactive flags', () => {
    const safeRaw = {
      type: 'navigate_to_scenic', scenic_id: 'zunyi-zoo', label: '伪造动作'
    }
    const spoofed = new Proxy(safeRaw, {
      get(target, key, receiver) {
        if (key === '__v_isReactive') return true
        if (key === '__v_raw') return safeRaw
        return Reflect.get(target, key, receiver)
      }
    })
    const wrapper = mount(MessageBubble, {
      props: {
        message: {
          role: 'assistant', content: '无操作', status: 'completed', actions_json: [spoofed]
        }
      },
      global: { stubs: { ElButton: true, ElIcon: true } }
    })

    expect(wrapper.find('button').exists()).toBe(false)
  })
})
