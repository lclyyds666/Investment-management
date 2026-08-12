import { beforeEach, describe, expect, it, vi } from 'vitest'

const axios = vi.hoisted(() => ({ create: vi.fn() }))
const messages = vi.hoisted(() => ({ error: vi.fn() }))
vi.mock('axios', () => ({ default: axios }))
vi.mock('element-plus', () => ({ ElMessage: messages }))

let rejectResponse
axios.create.mockReturnValue({
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn((_, rejected) => { rejectResponse = rejected }) }
  }
})

await import('./request')

describe('request conflict messages', () => {
  beforeEach(() => vi.clearAllMocks())

  it('leaves completed-task conflicts to the page actor warning', async () => {
    const error = { response: { status: 409, data: { detail: { code: 'task_already_completed', actor: '李复核' } } } }

    await expect(rejectResponse(error)).rejects.toBe(error)
    expect(messages.error).not.toHaveBeenCalled()
  })

  it('still reports other conflicts globally', async () => {
    const error = { response: { status: 409, data: { detail: '数据已发生变化' } } }

    await expect(rejectResponse(error)).rejects.toBe(error)
    expect(messages.error).toHaveBeenCalledWith('数据已发生变化')
  })
})
