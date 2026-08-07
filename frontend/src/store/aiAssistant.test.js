import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiAssistantStore } from './aiAssistant'
import { useUserStore } from './user'
import * as api from '@/api/aiAssistant'

vi.mock('@/api/aiAssistant')

function conflictError(code, message = code) {
  const error = new Error(message)
  error.status = 409
  error.code = code
  return error
}

function conversation(id, messages = []) {
  return { id, title: `会话${id}`, messages }
}

describe('AI assistant store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    localStorage.clear()
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => '11111111-1111-4111-8111-111111111111') })
    useUserStore().setUserInfo({ id: 7, role: 'business_handler' })
  })

  it('blocks duplicate sends only in the generating conversation', () => {
    const store = useAiAssistantStore()
    store.conversations = [{ id: 1 }, { id: 2 }]
    store.generatingByConversation = { 1: true }
    expect(store.canSend(1)).toBe(false)
    expect(store.canSend(2)).toBe(true)
  })

  it('restores the last conversation for the current user', async () => {
    localStorage.setItem('ai:lastConversationId:7', '2')
    api.listConversations.mockResolvedValue({ items: [conversation(1), conversation(2)] })
    api.getSuggestions.mockResolvedValue(['平台介绍'])
    api.getConversation.mockResolvedValue(conversation(2, [{ id: 20, role: 'assistant' }]))

    const store = useAiAssistantStore()
    await store.initialize()

    expect(store.activeConversationId).toBe(2)
    expect(store.messagesByConversation[2]).toEqual([{ id: 20, role: 'assistant' }])
    expect(api.getConversation).toHaveBeenCalledWith(2)
  })

  it('reuses the client message id when retrying the same failed prompt', async () => {
    api.streamMessage
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce()
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    await expect(store.sendMessage(1, '同一个问题')).rejects.toThrow('offline')
    await store.sendMessage(1, '同一个问题')

    const firstPayload = api.streamMessage.mock.calls[0][1]
    const secondPayload = api.streamMessage.mock.calls[1][1]
    expect(firstPayload.client_message_id).toBe(secondPayload.client_message_id)
    expect(crypto.randomUUID).toHaveBeenCalledTimes(1)
  })

  it('reloads and clears the retry submission only for duplicate conflicts', async () => {
    api.streamMessage
      .mockRejectedValueOnce(conflictError('duplicate_submission'))
      .mockResolvedValueOnce()
    crypto.randomUUID
      .mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222')
    api.getConversation.mockResolvedValue(conversation(1))
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    await expect(store.sendMessage(1, 'duplicate prompt')).resolves.toBeUndefined()
    await store.sendMessage(1, 'duplicate prompt')

    expect(api.getConversation).toHaveBeenCalledWith(1)
    expect(api.streamMessage.mock.calls[0][1].client_message_id)
      .not.toBe(api.streamMessage.mock.calls[1][1].client_message_id)
    expect(crypto.randomUUID).toHaveBeenCalledTimes(2)
  })

  it.each(['conversation_busy', 'unexpected_conflict'])(
    'keeps retry state and rejects non-duplicate 409 conflicts (%s)',
    async (code) => {
      api.streamMessage
        .mockRejectedValueOnce(conflictError(code))
        .mockResolvedValueOnce()
      const store = useAiAssistantStore()
      store.conversations = [conversation(1)]

      await expect(store.sendMessage(1, 'retry prompt')).rejects.toMatchObject({ code })
      expect(store.errorByConversation[1]).toMatchObject({ code })
      await store.sendMessage(1, 'retry prompt')

      expect(api.getConversation).not.toHaveBeenCalled()
      expect(api.streamMessage.mock.calls[0][1].client_message_id)
        .toBe(api.streamMessage.mock.calls[1][1].client_message_id)
      expect(crypto.randomUUID).toHaveBeenCalledTimes(1)
      expect(store.errorByConversation[1]).toBeNull()
    }
  )

  it('switching conversations does not abort another conversation stream', async () => {
    let streamOptions
    let finishStream
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      streamOptions = options
      return new Promise((resolve) => { finishStream = resolve })
    })
    api.getConversation.mockResolvedValue(conversation(2))
    const store = useAiAssistantStore()
    store.conversations = [conversation(1), conversation(2)]

    const sending = store.sendMessage(1, '后台生成')
    await Promise.resolve()
    await store.openConversation(2)

    expect(streamOptions.signal.aborted).toBe(false)
    finishStream()
    await sending
  })

  it('calls stop before aborting the local stream', async () => {
    let streamOptions
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      streamOptions = options
      options.onEvent({
        event: 'message.created',
        data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
      })
      return new Promise((resolve) => {
        options.signal.addEventListener('abort', resolve, { once: true })
      })
    })
    api.stopMessage.mockImplementation(async () => {
      expect(streamOptions.signal.aborted).toBe(false)
      return { id: 99, status: 'generating' }
    })
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    const sending = store.sendMessage(1, '停止测试')
    await Promise.resolve()
    await store.stopGeneration(1)
    await sending

    expect(api.stopMessage).toHaveBeenCalledWith(99)
    expect(streamOptions.signal.aborted).toBe(true)
    expect(store.messagesByConversation[1][1].status).toBe('stopped')
  })

  it('aborts the local stream when the stop endpoint rejects', async () => {
    let streamOptions
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      streamOptions = options
      options.onEvent({
        event: 'message.created',
        data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
      })
      return new Promise((resolve) => {
        options.signal.addEventListener('abort', resolve, { once: true })
      })
    })
    api.stopMessage.mockRejectedValue(new Error('stop unavailable'))
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    const sending = store.sendMessage(1, '停止失败测试')
    await Promise.resolve()
    await expect(store.stopGeneration(1)).resolves.toBeUndefined()
    await sending

    expect(streamOptions.signal.aborted).toBe(true)
    expect(store.messagesByConversation[1][1].status).toBe('stopped')
    expect(store.errorByConversation[1]).toMatchObject({ message: 'stop unavailable' })
  })

  it('aborts the local stream when the stop endpoint times out', async () => {
    vi.useFakeTimers()
    let streamOptions
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      streamOptions = options
      options.onEvent({
        event: 'message.created',
        data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
      })
      return new Promise((resolve) => {
        options.signal.addEventListener('abort', resolve, { once: true })
      })
    })
    api.stopMessage.mockImplementation(() => new Promise(() => {}))
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    const sending = store.sendMessage(1, '停止超时测试')
    await Promise.resolve()
    const stopping = store.stopGeneration(1)
    await vi.advanceTimersByTimeAsync(5000)
    await stopping
    await sending
    vi.useRealTimers()

    expect(api.stopMessage).toHaveBeenCalledWith(99)
    expect(streamOptions.signal.aborted).toBe(true)
    expect(store.messagesByConversation[1][1].status).toBe('stopped')
  })

  it('resets user-scoped state and ignores stale initialization results', async () => {
    let resolveOldConversations
    let resolveOldSuggestions
    const oldConversations = new Promise((resolve) => { resolveOldConversations = resolve })
    const oldSuggestions = new Promise((resolve) => { resolveOldSuggestions = resolve })
    api.listConversations
      .mockImplementationOnce(() => oldConversations)
      .mockResolvedValueOnce({ items: [conversation(2)] })
    api.getSuggestions
      .mockImplementationOnce(() => oldSuggestions)
      .mockResolvedValueOnce(['新用户建议'])
    api.getConversation.mockResolvedValue(conversation(2, [{ id: 20, role: 'assistant' }]))
    let oldStreamOptions
    api.streamMessage
      .mockImplementationOnce((_id, _payload, options) => {
        oldStreamOptions = options
        options.onEvent({
          event: 'message.created',
          data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
        })
        return new Promise((resolve) => {
          options.signal.addEventListener('abort', resolve, { once: true })
        })
      })
      .mockResolvedValueOnce()
    const store = useAiAssistantStore()

    const oldInitialization = store.initialize()
    await Promise.resolve()
    const oldSending = store.sendMessage(1, '相同问题')
    await Promise.resolve()
    store.errorByConversation = { 1: new Error('old error') }
    useUserStore().setUserInfo({ id: 8, role: 'business_handler' })

    await store.initialize()
    await oldSending

    expect(oldStreamOptions.signal.aborted).toBe(true)
    expect(store.conversations).toEqual([{ id: 2, title: '会话2', messages: undefined }])
    expect(store.activeConversationId).toBe(2)
    expect(store.messagesByConversation).toEqual({ 2: [{ id: 20, role: 'assistant' }] })
    expect(store.generatingByConversation).toEqual({})
    expect(store.errorByConversation).toEqual({})
    expect(store.suggestions).toEqual(['新用户建议'])

    resolveOldConversations({ items: [conversation(1)] })
    resolveOldSuggestions(['旧用户建议'])
    await oldInitialization

    expect(store.conversations).toEqual([{ id: 2, title: '会话2', messages: undefined }])
    expect(store.suggestions).toEqual(['新用户建议'])
    await store.sendMessage(2, '相同问题')
    expect(crypto.randomUUID).toHaveBeenCalledTimes(2)
  })

  it('does not apply a stale direct conversation open after a user switch', async () => {
    let resolveOldConversation
    const oldConversation = new Promise((resolve) => { resolveOldConversation = resolve })
    api.getConversation
      .mockImplementationOnce(() => oldConversation)
      .mockResolvedValueOnce(conversation(2, [{ id: 20, role: 'assistant' }]))
    api.listConversations.mockResolvedValue({ items: [conversation(2)] })
    api.getSuggestions.mockResolvedValue(['new suggestion'])
    const store = useAiAssistantStore()

    const opening = store.openConversation(1)
    await Promise.resolve()
    useUserStore().setUserInfo({ id: 8, role: 'business_handler' })
    await store.initialize()
    resolveOldConversation(conversation(1, [{ id: 10, role: 'assistant' }]))
    await opening

    expect(store.activeConversationId).toBe(2)
    expect(store.messagesByConversation).toEqual({ 2: [{ id: 20, role: 'assistant' }] })
    expect(localStorage.getItem('ai:lastConversationId:8')).toBe('2')
    expect(localStorage.getItem('ai:lastConversationId:7')).toBeNull()
  })

  it('does not apply a stale conversation creation after a user switch', async () => {
    let resolveCreated
    const created = new Promise((resolve) => { resolveCreated = resolve })
    api.createConversation.mockImplementationOnce(() => created)
    api.listConversations.mockResolvedValue({ items: [conversation(2)] })
    api.getSuggestions.mockResolvedValue(['new suggestion'])
    api.getConversation.mockResolvedValue(conversation(2, [{ id: 20, role: 'assistant' }]))
    const store = useAiAssistantStore()

    const creating = store.createConversation('old conversation')
    await Promise.resolve()
    useUserStore().setUserInfo({ id: 8, role: 'business_handler' })
    await store.initialize()
    resolveCreated(conversation(1, [{ id: 10, role: 'assistant' }]))

    await expect(creating).resolves.toBeNull()
    expect(store.activeConversationId).toBe(2)
    expect(store.messagesByConversation).toEqual({ 2: [{ id: 20, role: 'assistant' }] })
  })

  it('does not let a stale stop response write into a new user session', async () => {
    let resolveStop
    const stopResponse = new Promise((resolve) => { resolveStop = resolve })
    let streamOptions
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      streamOptions = options
      options.onEvent({
        event: 'message.created',
        data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
      })
      return new Promise((resolve) => {
        options.signal.addEventListener('abort', resolve, { once: true })
      })
    })
    api.stopMessage.mockImplementation(() => stopResponse)
    api.listConversations.mockResolvedValue({ items: [conversation(2)] })
    api.getSuggestions.mockResolvedValue(['new suggestion'])
    api.getConversation.mockResolvedValue(conversation(2, [{ id: 20, role: 'assistant' }]))
    const store = useAiAssistantStore()

    const sending = store.sendMessage(1, 'old request')
    await Promise.resolve()
    const stopping = store.stopGeneration(1)
    await Promise.resolve()
    useUserStore().setUserInfo({ id: 8, role: 'business_handler' })
    await store.initialize()
    resolveStop({ id: 99, status: 'stopped' })
    await stopping
    await sending

    expect(streamOptions.signal.aborted).toBe(true)
    expect(store.activeConversationId).toBe(2)
    expect(store.messagesByConversation).toEqual({ 2: [{ id: 20, role: 'assistant' }] })
    expect(store.errorByConversation).toEqual({})
  })

  it('retains the client message id after an SSE error event', async () => {
    api.streamMessage
      .mockImplementationOnce((_id, _payload, options) => {
        options.onEvent({
          event: 'message.created',
          data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
        })
        options.onEvent({ event: 'error', data: { message_id: 99, code: 'provider_error', message: 'provider failed' } })
        return Promise.resolve()
      })
      .mockResolvedValueOnce()
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    await store.sendMessage(1, 'retry after event error')
    await store.sendMessage(1, 'retry after event error')

    expect(api.streamMessage.mock.calls[0][1].client_message_id)
      .toBe(api.streamMessage.mock.calls[1][1].client_message_id)
    expect(crypto.randomUUID).toHaveBeenCalledTimes(1)
    expect(store.messagesByConversation[1][1].status).toBe('failed')
  })

  it('reconciles a truncated stream as failed', async () => {
    api.streamMessage.mockImplementation((_id, _payload, options) => {
      options.onEvent({
        event: 'message.created',
        data: { request_id: 'r1', message_id: 99, user_message_id: 98 }
      })
      return Promise.reject(new Error('SSE 流在终态事件前结束'))
    })
    const store = useAiAssistantStore()
    store.conversations = [conversation(1)]

    await expect(store.sendMessage(1, 'truncated stream')).rejects.toThrow('终态事件')
    expect(store.messagesByConversation[1][1]).toMatchObject({
      status: 'failed', error_code: 'stream_incomplete'
    })
  })

  it('aborts after waiting for a message id without calling stop', async () => {
    vi.useFakeTimers()
    try {
      let streamOptions
      api.streamMessage.mockImplementation((_id, _payload, options) => {
        streamOptions = options
        return new Promise((resolve) => {
          options.signal.addEventListener('abort', resolve, { once: true })
        })
      })
      const store = useAiAssistantStore()
      store.conversations = [conversation(1)]

      const sending = store.sendMessage(1, 'stop before created')
      await Promise.resolve()
      const stopping = store.stopGeneration(1)
      await vi.advanceTimersByTimeAsync(5000)
      await stopping
      await sending

      expect(api.stopMessage).not.toHaveBeenCalled()
      expect(streamOptions.signal.aborted).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
