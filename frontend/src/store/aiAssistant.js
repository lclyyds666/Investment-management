import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/aiAssistant'
import { useUserStore } from '@/store/user'
import { createUuid } from '@/utils/uuid'

const STOP_TIMEOUT_MS = 5000

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

export const useAiAssistantStore = defineStore('aiAssistant', () => {
  const conversations = ref([])
  const activeConversationId = ref(null)
  const messagesByConversation = ref({})
  const suggestions = ref([])
  const generatingByConversation = ref({})
  const errorByConversation = ref({})
  const initializing = ref(false)
  const initialError = ref(null)

  const controllers = new Map()
  const assistantMessageIds = new Map()
  const retrySubmissions = new Map()
  let initializationVersion = 0
  let sessionEpoch = 0
  let sessionUserId

  const activeConversation = computed(() => (
    conversations.value.find((item) => item.id === activeConversationId.value) || null
  ))
  const activeMessages = computed(() => (
    messagesByConversation.value[activeConversationId.value] || []
  ))

  function currentUserId() {
    return useUserStore().userInfo?.id ?? null
  }

  function lastConversationKey() {
    const userId = currentUserId()
    return userId == null ? null : `ai:lastConversationId:${userId}`
  }

  function persistActiveConversation(conversationId) {
    const key = lastConversationKey()
    if (!key) return
    if (conversationId == null) localStorage.removeItem(key)
    else localStorage.setItem(key, String(conversationId))
  }

  function setConversationMessages(conversationId, messages) {
    messagesByConversation.value = {
      ...messagesByConversation.value,
      [conversationId]: messages || []
    }
  }

  function updateConversation(conversation) {
    const index = conversations.value.findIndex((item) => item.id === conversation.id)
    if (index === -1) conversations.value = [conversation, ...conversations.value]
    else conversations.value.splice(index, 1, conversation)
  }

  function resetSessionState() {
    controllers.forEach((controller) => controller.abort())
    controllers.clear()
    assistantMessageIds.clear()
    retrySubmissions.clear()
    conversations.value = []
    activeConversationId.value = null
    messagesByConversation.value = {}
    suggestions.value = []
    generatingByConversation.value = {}
    errorByConversation.value = {}
    initializing.value = false
    initialError.value = null
  }

  function startSession() {
    const userId = currentUserId()
    if (sessionUserId !== userId) {
      sessionEpoch += 1
      sessionUserId = userId
      resetSessionState()
    }
    return { userId, epoch: sessionEpoch }
  }

  function isCurrentSession(session) {
    return session.epoch === sessionEpoch
      && session.userId === sessionUserId
      && session.userId === currentUserId()
  }

  async function openConversation(conversationId, session = startSession(), isCurrent = null) {
    const detail = await api.getConversation(conversationId)
    if (!isCurrentSession(session) || (isCurrent && !isCurrent())) return null
    activeConversationId.value = detail.id
    updateConversation({ ...detail, messages: undefined })
    setConversationMessages(detail.id, detail.messages || [])
    persistActiveConversation(detail.id)
    return detail
  }

  async function initialize() {
    const session = startSession()
    const version = ++initializationVersion
    const isCurrentInitialization = () => (
      version === initializationVersion && isCurrentSession(session)
    )
    initializing.value = true
    initialError.value = null
    try {
      const [page, loadedSuggestions] = await Promise.all([
        api.listConversations({ page: 1, size: 50 }),
        api.getSuggestions()
      ])
      if (!isCurrentInitialization()) return
      conversations.value = page?.items || []
      suggestions.value = loadedSuggestions || []
      const key = lastConversationKey()
      const storedId = key ? Number(localStorage.getItem(key)) : NaN
      const target = conversations.value.find((item) => item.id === storedId)
        || conversations.value[0]
      if (target) await openConversation(target.id, session, isCurrentInitialization)
      else {
        activeConversationId.value = null
        persistActiveConversation(null)
      }
    } catch (error) {
      if (!isCurrentInitialization()) return
      initialError.value = error
      throw error
    } finally {
      if (isCurrentInitialization()) initializing.value = false
    }
  }

  async function createConversation(title) {
    const session = startSession()
    const created = await api.createConversation(title ? { title } : {})
    if (!isCurrentSession(session)) return null
    updateConversation({ ...created, messages: undefined })
    setConversationMessages(created.id, created.messages || [])
    activeConversationId.value = created.id
    persistActiveConversation(created.id)
    return created
  }

  async function renameConversation(conversationId, title) {
    const session = startSession()
    const updated = await api.renameConversation(conversationId, title)
    if (!isCurrentSession(session)) return null
    updateConversation({ ...updated, messages: undefined })
    return updated
  }

  async function deleteConversation(conversationId) {
    const session = startSession()
    if (generatingByConversation.value[conversationId]) {
      await stopGeneration(conversationId, session)
    }
    if (!isCurrentSession(session)) return
    await api.deleteConversation(conversationId)
    if (!isCurrentSession(session)) return
    conversations.value = conversations.value.filter((item) => item.id !== conversationId)
    const nextMessages = { ...messagesByConversation.value }
    delete nextMessages[conversationId]
    messagesByConversation.value = nextMessages
    retrySubmissions.delete(conversationId)
    assistantMessageIds.delete(conversationId)
    if (activeConversationId.value === conversationId) {
      const next = conversations.value[0]
      if (next) await openConversation(next.id, session)
      else {
        activeConversationId.value = null
        persistActiveConversation(null)
      }
    }
  }

  function canSend(conversationId) {
    return Boolean(conversationId) && !generatingByConversation.value[conversationId]
  }

  function messagesFor(conversationId) {
    return messagesByConversation.value[conversationId] || []
  }

  function replaceMessage(conversationId, messageId, changes) {
    const messages = messagesFor(conversationId)
    const index = messages.findIndex((message) => message.id === messageId)
    if (index === -1) return null
    messages[index] = { ...messages[index], ...changes }
    return messages[index]
  }

  function handleStreamEvent(session, conversationId, clientMessageId, { event, data }) {
    if (!isCurrentSession(session)) return null
    if (event === 'message.created') {
      const messages = messagesFor(conversationId)
      const optimistic = messages.find((message) => message.client_message_id === clientMessageId)
      if (optimistic) optimistic.id = data.user_message_id
      let assistant = messages.find((message) => message.id === data.message_id)
      if (!assistant) {
        assistant = {
          id: data.message_id,
          conversation_id: conversationId,
          role: 'assistant',
          content: '',
          status: 'generating',
          request_id: data.request_id,
          actions_json: [],
          tool_statuses: []
        }
        messages.push(assistant)
      }
      assistantMessageIds.set(conversationId, data.message_id)
      return
    }

    const messageId = data.message_id || assistantMessageIds.get(conversationId)
    const assistant = messagesFor(conversationId).find((message) => message.id === messageId)
    if (!assistant) return

    if (event === 'text.delta') assistant.content += data.text || ''
    else if (event === 'action' && data.action) assistant.actions_json.push(data.action)
    else if (event === 'tool.status') {
      assistant.tool_statuses.push({ tool: data.tool, status: data.status })
      if (data.metadata) Object.assign(assistant, data.metadata)
    } else if (event === 'message.completed') {
      assistant.status = 'completed'
      return 'completed'
    } else if (event === 'message.stopped') {
      assistant.status = 'stopped'
      return 'stopped'
    }
    else if (event === 'error') {
      assistant.status = 'failed'
      assistant.error_code = data.code
      errorByConversation.value = {
        ...errorByConversation.value,
        [conversationId]: data.message || 'AI 服务暂时不可用，请稍后重试。'
      }
    }
  }

  async function sendMessage(conversationId, content) {
    const session = startSession()
    if (!canSend(conversationId)) throw new Error('该会话正在生成回答')
    const normalized = String(content || '').trim()
    if (!normalized) throw new Error('请输入问题')

    const retry = retrySubmissions.get(conversationId)
    const clientMessageId = retry?.content === normalized
      ? retry.clientMessageId
      : createUuid()
    retrySubmissions.set(conversationId, { content: normalized, clientMessageId })

    const messages = messagesFor(conversationId)
    let userMessage = messages.find((message) => message.client_message_id === clientMessageId)
    if (!userMessage) {
      userMessage = {
        id: `client:${clientMessageId}`,
        conversation_id: conversationId,
        role: 'user',
        content: normalized,
        status: 'completed',
        client_message_id: clientMessageId,
        actions_json: []
      }
      messages.push(userMessage)
      setConversationMessages(conversationId, messages)
    }

    const controller = new AbortController()
    controllers.set(conversationId, controller)
    generatingByConversation.value = {
      ...generatingByConversation.value,
      [conversationId]: true
    }
    errorByConversation.value = { ...errorByConversation.value, [conversationId]: null }

    let terminalEvent = null
    try {
      await api.streamMessage(
        conversationId,
        { content: normalized, client_message_id: clientMessageId },
        {
          signal: controller.signal,
          onEvent: (event) => {
            const result = handleStreamEvent(session, conversationId, clientMessageId, event)
            if (result === 'completed' || result === 'stopped') terminalEvent = result
          }
        }
      )
      if (isCurrentSession(session) && terminalEvent) retrySubmissions.delete(conversationId)
    } catch (error) {
      if (!isCurrentSession(session)) return
      if (error?.name === 'AbortError') return
      if (error?.status === 409 && error?.code === 'duplicate_submission') {
        retrySubmissions.delete(conversationId)
        await openConversation(conversationId, session)
        return
      }
      const messageId = assistantMessageIds.get(conversationId)
      const assistant = messagesFor(conversationId).find((message) => message.id === messageId)
      if (assistant?.status === 'generating') {
        assistant.status = 'failed'
        assistant.error_code = 'stream_incomplete'
      }
      errorByConversation.value = { ...errorByConversation.value, [conversationId]: error }
      throw error
    } finally {
      if (isCurrentSession(session) && controllers.get(conversationId) === controller) {
        controllers.delete(conversationId)
        generatingByConversation.value = {
          ...generatingByConversation.value,
          [conversationId]: false
        }
      }
    }
  }

  async function stopGeneration(conversationId, session = startSession()) {
    const controller = controllers.get(conversationId)
    if (!controller) return

    const stopRequest = (async () => {
      const deadline = Date.now() + STOP_TIMEOUT_MS
      let messageId = assistantMessageIds.get(conversationId)
      while (!messageId && Date.now() < deadline && isCurrentSession(session) && !controller.signal.aborted) {
        await delay(25)
        messageId = assistantMessageIds.get(conversationId)
      }
      if (messageId && isCurrentSession(session) && !controller.signal.aborted) {
        await api.stopMessage(messageId)
        return true
      }
      return false
    })()
    void stopRequest.catch(() => {})

    try {
      const stopped = await Promise.race([stopRequest, delay(STOP_TIMEOUT_MS).then(() => false)])
      if (stopped && isCurrentSession(session)) retrySubmissions.delete(conversationId)
    } catch (error) {
      if (isCurrentSession(session)) {
        errorByConversation.value = { ...errorByConversation.value, [conversationId]: error }
      }
    } finally {
      controller.abort()
      if (!isCurrentSession(session)) return
      const messageId = assistantMessageIds.get(conversationId)
      const assistant = messagesFor(conversationId).find((message) => message.id === messageId)
      if (assistant?.status === 'generating') assistant.status = 'stopped'
    }
  }

  function saveScrollPosition(conversationId, position) {
    localStorage.setItem(`ai:scroll:${conversationId}`, String(Math.max(0, Number(position) || 0)))
  }

  function getScrollPosition(conversationId) {
    return Number(localStorage.getItem(`ai:scroll:${conversationId}`)) || 0
  }

  return {
    conversations,
    activeConversationId,
    messagesByConversation,
    suggestions,
    generatingByConversation,
    errorByConversation,
    initializing,
    initialError,
    activeConversation,
    activeMessages,
    initialize,
    createConversation,
    openConversation,
    renameConversation,
    deleteConversation,
    canSend,
    sendMessage,
    stopGeneration,
    saveScrollPosition,
    getScrollPosition
  }
})
