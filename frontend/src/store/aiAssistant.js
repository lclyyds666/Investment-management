import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/aiAssistant'
import { useUserStore } from '@/store/user'

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
  let initializedUserId

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

  function isCurrentInitialization(version, userId) {
    return version === initializationVersion && userId === currentUserId()
  }

  async function openConversation(conversationId, isCurrent = null) {
    const detail = await api.getConversation(conversationId)
    if (isCurrent && !isCurrent()) return null
    activeConversationId.value = detail.id
    updateConversation({ ...detail, messages: undefined })
    setConversationMessages(detail.id, detail.messages || [])
    persistActiveConversation(detail.id)
    return detail
  }

  async function initialize() {
    const userId = currentUserId()
    const version = ++initializationVersion
    if (initializedUserId !== userId) {
      resetSessionState()
      initializedUserId = userId
    }
    initializing.value = true
    initialError.value = null
    try {
      const [page, loadedSuggestions] = await Promise.all([
        api.listConversations({ page: 1, size: 50 }),
        api.getSuggestions()
      ])
      if (!isCurrentInitialization(version, userId)) return
      conversations.value = page?.items || []
      suggestions.value = loadedSuggestions || []
      const key = lastConversationKey()
      const storedId = key ? Number(localStorage.getItem(key)) : NaN
      const target = conversations.value.find((item) => item.id === storedId)
        || conversations.value[0]
      if (target) await openConversation(target.id, () => isCurrentInitialization(version, userId))
      else {
        activeConversationId.value = null
        persistActiveConversation(null)
      }
    } catch (error) {
      if (!isCurrentInitialization(version, userId)) return
      initialError.value = error
      throw error
    } finally {
      if (isCurrentInitialization(version, userId)) initializing.value = false
    }
  }

  async function createConversation(title) {
    const created = await api.createConversation(title ? { title } : {})
    updateConversation({ ...created, messages: undefined })
    setConversationMessages(created.id, created.messages || [])
    activeConversationId.value = created.id
    persistActiveConversation(created.id)
    return created
  }

  async function renameConversation(conversationId, title) {
    const updated = await api.renameConversation(conversationId, title)
    updateConversation({ ...updated, messages: undefined })
    return updated
  }

  async function deleteConversation(conversationId) {
    if (generatingByConversation.value[conversationId]) {
      await stopGeneration(conversationId)
    }
    await api.deleteConversation(conversationId)
    conversations.value = conversations.value.filter((item) => item.id !== conversationId)
    const nextMessages = { ...messagesByConversation.value }
    delete nextMessages[conversationId]
    messagesByConversation.value = nextMessages
    retrySubmissions.delete(conversationId)
    assistantMessageIds.delete(conversationId)
    if (activeConversationId.value === conversationId) {
      const next = conversations.value[0]
      if (next) await openConversation(next.id)
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

  function handleStreamEvent(conversationId, clientMessageId, { event, data }) {
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
    } else if (event === 'message.completed') assistant.status = 'completed'
    else if (event === 'message.stopped') assistant.status = 'stopped'
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
    if (!canSend(conversationId)) throw new Error('该会话正在生成回答')
    const normalized = String(content || '').trim()
    if (!normalized) throw new Error('请输入问题')

    const retry = retrySubmissions.get(conversationId)
    const clientMessageId = retry?.content === normalized
      ? retry.clientMessageId
      : crypto.randomUUID()
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

    try {
      await api.streamMessage(
        conversationId,
        { content: normalized, client_message_id: clientMessageId },
        {
          signal: controller.signal,
          onEvent: (event) => handleStreamEvent(conversationId, clientMessageId, event)
        }
      )
      retrySubmissions.delete(conversationId)
    } catch (error) {
      if (error?.name === 'AbortError') return
      if (error?.status === 409) {
        retrySubmissions.delete(conversationId)
        await openConversation(conversationId)
        return
      }
      errorByConversation.value = { ...errorByConversation.value, [conversationId]: error }
      throw error
    } finally {
      if (controllers.get(conversationId) === controller) {
        controllers.delete(conversationId)
        generatingByConversation.value = {
          ...generatingByConversation.value,
          [conversationId]: false
        }
      }
    }
  }

  async function stopGeneration(conversationId) {
    const controller = controllers.get(conversationId)
    if (!controller) return

    const stopRequest = (async () => {
      const deadline = Date.now() + STOP_TIMEOUT_MS
      let messageId = assistantMessageIds.get(conversationId)
      while (!messageId && Date.now() < deadline) {
        await delay(25)
        messageId = assistantMessageIds.get(conversationId)
      }
      if (messageId) await api.stopMessage(messageId)
    })()
    void stopRequest.catch(() => {})

    try {
      await Promise.race([stopRequest, delay(STOP_TIMEOUT_MS)])
    } catch (error) {
      errorByConversation.value = { ...errorByConversation.value, [conversationId]: error }
    } finally {
      controller.abort()
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
