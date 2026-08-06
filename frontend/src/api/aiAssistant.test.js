import { describe, expect, it, vi } from 'vitest'
import { streamMessage } from './aiAssistant'

describe('streamMessage', () => {
  it('normalizes a structured FastAPI conflict detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: vi.fn().mockResolvedValue({
        detail: { code: 'conversation_busy', message: 'Conversation is generating.' }
      })
    }))

    await expect(streamMessage(1, { content: 'test' }, {
      signal: new AbortController().signal,
      onEvent: vi.fn()
    })).rejects.toMatchObject({
      status: 409,
      code: 'conversation_busy',
      message: 'Conversation is generating.'
    })
  })

  it('decodes an event split within a UTF-8 character', async () => {
    const eventText = 'event: text.delta\ndata: {"text":"你好"}\n\n'
    const bytes = new TextEncoder().encode(eventText)
    const splitAt = bytes.indexOf(0xe4) + 1
    const events = []
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(bytes.slice(0, splitAt))
          controller.enqueue(bytes.slice(splitAt))
          controller.close()
        }
      })
    }))

    await streamMessage(1, { content: 'test' }, {
      signal: new AbortController().signal,
      onEvent: (event) => events.push(event)
    })

    expect(events).toEqual([{ event: 'text.delta', data: { text: '你好' } }])
  })
})
