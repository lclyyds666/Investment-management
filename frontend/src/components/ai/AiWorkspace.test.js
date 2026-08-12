import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AiWorkspace from './AiWorkspace.vue'
import MessageComposer from './MessageComposer.vue'
import MessageList from './MessageList.vue'
import { useAiAssistantStore } from '@/store/aiAssistant'

const stubs = {
  ElAlert: { template: '<div><slot /></div>' },
  ElButton: { emits: ['click'], template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>' },
  ElDrawer: { template: '<div><slot /></div>' },
  ElInput: {
    props: ['modelValue'],
    template: '<textarea v-bind="$attrs" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @keydown="$emit(\'keydown\', $event)" @compositionstart="$emit(\'compositionstart\')" @compositionend="$emit(\'compositionend\')" />'
  },
  ElSkeleton: true
}

describe('AI workspace', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  function mountWorkspace() {
    const store = useAiAssistantStore()
    vi.spyOn(store, 'initialize').mockResolvedValue()
    return { store, wrapper: mount(AiWorkspace, { global: { stubs } }) }
  }

  it('keeps conversation and business regions independent', () => {
    const { wrapper } = mountWorkspace()
    expect(wrapper.attributes('data-workspace')).toBe('ai')
    expect(wrapper.find('[data-testid="conversation-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="message-composer"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="application-entry"]').exists()).toBe(false)
  })

  it('shows stop instead of send while the active conversation generates', async () => {
    const { store, wrapper } = mountWorkspace()
    store.activeConversationId = 1
    store.generatingByConversation = { 1: true }
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[aria-label="停止生成"]').exists()).toBe(true)
  })

  it('creates a conversation before submitting an empty-session suggestion', async () => {
    const { store, wrapper } = mountWorkspace()
    store.suggestions = ['查看本月经营数据']
    vi.spyOn(store, 'createConversation').mockResolvedValue({ id: 8 })
    vi.spyOn(store, 'sendMessage').mockResolvedValue()
    await wrapper.vm.$nextTick()
    await wrapper.find('.suggestions__item').trigger('click')
    expect(store.createConversation).toHaveBeenCalledWith('查看本月经营数据')
    expect(store.sendMessage).toHaveBeenCalledWith(8, '查看本月经营数据')
  })

  it('does not submit Enter while IME composition is active', async () => {
    const wrapper = mount(MessageComposer, { props: { generating: false }, global: { stubs } })
    const input = wrapper.get('textarea')
    await input.setValue('输入中')
    await input.trigger('compositionstart')
    await input.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(wrapper.emitted('submit')).toBeUndefined()
    await input.trigger('compositionend')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')[0][0]).toBe('输入中')
  })

  it('keeps the draft and offers retry when conversation creation fails', async () => {
    const { store, wrapper } = mountWorkspace()
    vi.spyOn(store, 'createConversation').mockRejectedValue(new Error('创建失败'))
    const input = wrapper.get('textarea')
    await input.setValue('保留这条问题')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(input.element.value).toBe('保留这条问题')
    expect(wrapper.get('[aria-label="重试发送"]').text()).toBe('重试')
  })

  it('guards duplicate submits while an empty session is being created', async () => {
    let resolveCreation
    const creation = new Promise((resolve) => { resolveCreation = resolve })
    const { store, wrapper } = mountWorkspace()
    vi.spyOn(store, 'createConversation').mockReturnValue(creation)
    vi.spyOn(store, 'sendMessage').mockResolvedValue()
    const input = wrapper.get('textarea')
    await input.setValue('只发送一次')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(store.createConversation).toHaveBeenCalledOnce()
    resolveCreation({ id: 9 })
    await flushPromises()
  })

  it('uses the normalized first question truncated to 120 characters as title', async () => {
    const { store, wrapper } = mountWorkspace()
    vi.spyOn(store, 'createConversation').mockResolvedValue({ id: 10 })
    vi.spyOn(store, 'sendMessage').mockResolvedValue()
    const prompt = `  ${'问'.repeat(130)}  `
    await wrapper.get('textarea').setValue(prompt)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(store.createConversation).toHaveBeenCalledWith('问'.repeat(120))
    expect(store.sendMessage).toHaveBeenCalledWith(10, '问'.repeat(130))
  })

  it('retries a failed stream with the same pending content', async () => {
    const { store, wrapper } = mountWorkspace()
    store.activeConversationId = 3
    store.messagesByConversation = { 3: [] }
    vi.spyOn(store, 'sendMessage').mockRejectedValueOnce(new Error('流失败')).mockResolvedValueOnce()
    await wrapper.get('textarea').setValue('重试原问题')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[aria-label="重试发送"]').exists()).toBe(true)
    await wrapper.get('[aria-label="重试发送"]').trigger('click')
    await flushPromises()
    expect(store.sendMessage).toHaveBeenCalledTimes(2)
    expect(store.sendMessage.mock.calls[0]).toEqual([3, '重试原问题'])
    expect(store.sendMessage.mock.calls[1]).toEqual([3, '重试原问题'])
  })

  it('keeps a fixed workspace height and a shrinkable internal scroll chain', () => {
    const workspaceSource = readFileSync(resolve(process.cwd(), 'src/components/ai/AiWorkspace.vue'), 'utf8')
    const messageListSource = readFileSync(resolve(process.cwd(), 'src/components/ai/MessageList.vue'), 'utf8')
    expect(workspaceSource).toContain('height: clamp(500px, 62vh, 680px)')
    expect(workspaceSource).toMatch(/\.ai-workspace__body \{[^}]*min-height: 0;[^}]*overflow: hidden;/)
    expect(workspaceSource).toMatch(/\.ai-workspace__conversation \{[^}]*min-height: 0;[^}]*overflow: hidden;/)
    expect(messageListSource).toMatch(/\.message-list \{[^}]*min-height: 0;[^}]*overflow-y: auto;/)
  })

  it('restores the saved scroll position when switching sessions', async () => {
    const wrapper = mount(MessageList, {
      props: { conversationId: 2, scrollPosition: 76 },
      global: { stubs }
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="message-list"]').element.scrollTop).toBe(76)
  })
})
