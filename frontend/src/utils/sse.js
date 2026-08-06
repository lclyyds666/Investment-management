export function createSseParser(onEvent) {
  let buffer = ''

  function emit(frame) {
    const lines = frame.split(/\r\n|\r|\n/)
    let event = 'message'
    const dataLines = []
    for (const line of lines) {
      if (!line || line.startsWith(':')) continue
      const separator = line.indexOf(':')
      const field = separator === -1 ? line : line.slice(0, separator)
      let value = separator === -1 ? '' : line.slice(separator + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') event = value
      if (field === 'data') dataLines.push(value)
    }
    if (dataLines.length === 0) return
    onEvent({ event, data: JSON.parse(dataLines.join('\n')) })
  }

  function drain() {
    while (true) {
      const boundary = buffer.match(/\r\n(?:\r\n|\r|\n)|\r(?!\n)(?:\r\n|\r|\n)|\n(?:\r\n|\r|\n)/)
      if (!boundary || boundary.index === undefined) return
      const frame = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary[0].length)
      if (frame) emit(frame)
    }
  }

  return {
    push(chunk) {
      if (!chunk) return
      buffer += chunk
      drain()
    },
    finish() {
      drain()
      if (buffer.trim()) throw new Error('收到不完整的 SSE 事件')
      buffer = ''
    }
  }
}
