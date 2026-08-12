import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse'

describe('SSE parser', () => {
  it('parses a UTF-8 event split across chunks', () => {
    const events = []
    const parser = createSseParser((event) => events.push(event))
    parser.push('event: text.delta\ndata: {"text":"遵')
    parser.push('义"}\n\n')
    expect(events).toEqual([{ event: 'text.delta', data: { text: '遵义' } }])
  })

  it('supports CRLF frames and rejects an incomplete final frame', () => {
    const events = []
    const parser = createSseParser((event) => events.push(event))
    parser.push('event: message.completed\r\ndata: {"status":"completed"}\r\n\r\n')
    parser.finish()
    expect(events[0].event).toBe('message.completed')

    const incomplete = createSseParser(() => {})
    incomplete.push('event: text.delta\ndata: {}')
    expect(() => incomplete.finish()).toThrow('不完整')
  })

  it('supports CR-only line endings', () => {
    const events = []
    const parser = createSseParser((event) => events.push(event))
    parser.push('event: message.stopped\rdata: {"status":"stopped"}\r\r')
    parser.finish()
    expect(events).toEqual([{ event: 'message.stopped', data: { status: 'stopped' } }])
  })
})
