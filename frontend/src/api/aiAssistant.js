import request from './request'
import { createSseParser } from '@/utils/sse'

export const listConversations = (params = {}) => request.get('/ai-assistant/conversations', { params })
export const createConversation = (payload = {}) => request.post('/ai-assistant/conversations', payload)
export const getConversation = (id) => request.get(`/ai-assistant/conversations/${id}`)
export const renameConversation = (id, title) => request.patch(`/ai-assistant/conversations/${id}`, { title })
export const deleteConversation = (id) => request.delete(`/ai-assistant/conversations/${id}`)
export const getSuggestions = () => request.get('/ai-assistant/suggestions')
export const stopMessage = (id) => request.post(`/ai-assistant/messages/${id}/stop`)

async function responseError(response) {
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  const error = new Error(payload?.detail || payload?.message || `请求失败（${response.status}）`)
  error.status = response.status
  error.payload = payload
  return error
}

export async function streamMessage(conversationId, payload, { signal, onEvent }) {
  const response = await fetch(`/api/v1/ai-assistant/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('token')}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify(payload),
    signal
  })
  if (!response.ok) throw await responseError(response)
  if (!response.body) throw new Error('浏览器未提供流式响应')

  const parser = createSseParser(onEvent)
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.finish()
}
