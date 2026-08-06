import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AiWorkspace from './AiWorkspace.vue'
import MessageComposer from './MessageComposer.vue'
import MessageList from './MessageList.vue'
import { useAiAssistantStore } from '@/store/aiAssistant'

const stubs = {
  ElAlert: { template: '<div><slot /></div>' },
  ElButton: { template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>' },
  ElDrawer: { template: '<div><slot /></div>' },
  ElInput: { template: '<textarea v-bind="$attrs" @input="$emit(\'update:modelValue\', $event.target.value)" @keydown="$emit(\'keydown\', $event)" @compositionstart="$emit(\'compositionstart\')" @compositionend="$emit(\'compositionend\')" />' },
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
    expect(store.createConversation).toHaveBeenCalledOnce()
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
    expect(wrapper.emitted('submit')[0]).toEqual(['输入中'])
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
