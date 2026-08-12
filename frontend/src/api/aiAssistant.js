import request from './request'
import { createSseParser } from '@/utils/sse'

export const listConversations = (params = {}) => request.get('/ai-assistant/conversations', { params })
export const createConversation = (payload = {}) => request.post('/ai-assistant/conversations', payload)
export const getConversation = (id) => request.get(`/ai-assistant/conversations/${id}`)
export const renameConversation = (id, title) => request.patch(`/ai-assistant/conversations/${id}`, { title })
export const deleteConversation = (id) => request.delete(`/ai-assistant/conversations/${id}`)
export const getSuggestions = () => request.get('/ai-assistant/suggestions')
export const stopMessage = (id) => request.post(`/ai-assistant/messages/${id}/stop`)
export const listAdminConversations = (params = {}) => request.get('/ai-assistant/admin/conversations', { params })
export const getAdminConversation = (id) => request.get(`/ai-assistant/admin/conversations/${id}`)
export const deleteAdminConversation = (id, reason) => request.delete(`/ai-assistant/admin/conversations/${id}`, { data: { reason } })
export const listDeletionAudits = (params = {}) => request.get('/ai-assistant/admin/deletion-audits', { params })

async function responseError(response) {
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  const detail = payload?.detail
  const detailObject = detail && typeof detail === 'object' && !Array.isArray(detail)
    ? detail
    : null
  const message = (typeof detailObject?.message === 'string' ? detailObject.message : null)
    || (typeof detail === 'string' ? detail : null)
    || (typeof payload?.message === 'string' ? payload.message : null)
    || `请求失败（${response.status}）`
  const error = new Error(message)
  error.status = response.status
  error.payload = payload
  error.code = detailObject?.code || payload?.code
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

  let terminalSeen = false
  const parser = createSseParser((event) => {
    if (event.event === 'message.completed' || event.event === 'message.stopped' || event.event === 'error') {
      terminalSeen = true
    }
    onEvent(event)
  })
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.finish()
  if (!terminalSeen) throw new Error('SSE 流在终态事件前结束')
}
