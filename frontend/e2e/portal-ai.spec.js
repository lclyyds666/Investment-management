import http from 'node:http'
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

const conversationId = 42
const assistantMessageId = 1002
const userMessageId = 1001
const scenicAction = {
  type: 'navigate_to_scenic',
  scenic_id: 'zunyi-zoo',
  label: 'Open scenic detail'
}

let mockServer
let activeStream
let viteProcess
let stopEndpointCalls = 0

function now() {
  return new Date().toISOString()
}

function conversation(title = 'E2E conversation') {
  return {
    id: conversationId,
    owner_id: 7,
    title,
    status: 'active',
    last_active_at: now(),
    expires_at: now(),
    created_at: now(),
    updated_at: now(),
    messages: []
  }
}

function sse(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function json(response, data, direct = false) {
  response.writeHead(200, { 'Content-Type': 'application/json' })
  response.end(JSON.stringify(direct ? data : { code: 0, message: 'ok', data }))
}

function readJson(request) {
  return new Promise((resolve) => {
    let body = ''
    request.on('data', (chunk) => { body += chunk })
    request.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}) } catch { resolve({}) }
    })
  })
}

function startMockSseServer() {
  mockServer = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1:8001')
    if (request.method === 'GET' && url.pathname === '/health') return json(response, { ok: true }, true)

    const streamMatch = url.pathname.match(/^\/api\/v1\/ai-assistant\/conversations\/\d+\/messages$/)
    if (request.method === 'POST' && streamMatch) {
      const payload = await readJson(request)
      response.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive'
      })
      response.write(sse('message.created', {
        request_id: 'e2e-request',
        message_id: assistantMessageId,
        user_message_id: userMessageId
      }))

      const finish = () => {
        if (response.writableEnded) return
        response.write(sse('text.delta', { message_id: assistantMessageId, text: 'The platform answer is ready.' }))
        response.write(sse('action', { message_id: assistantMessageId, action: scenicAction }))
        response.write(sse('message.completed', { message_id: assistantMessageId }))
        response.end()
        activeStream = null
      }

      if (/stop/i.test(String(payload.content || ''))) {
        activeStream = {
          stop: () => {
            if (response.writableEnded) return
            response.write(sse('message.stopped', { message_id: assistantMessageId }))
            response.end()
            activeStream = null
          }
        }
      } else {
        setTimeout(finish, 500)
      }
      return
    }

    const stopMatch = url.pathname.match(/^\/api\/v1\/ai-assistant\/messages\/\d+\/stop$/)
    if (request.method === 'POST' && stopMatch) {
      stopEndpointCalls += 1
      activeStream?.stop()
      return json(response, { id: assistantMessageId, status: 'stopped' })
    }

    response.writeHead(404)
    response.end()
  })
  return new Promise((resolve, reject) => {
    mockServer.once('error', reject)
    mockServer.listen(8001, '127.0.0.1', () => {
      mockServer.unref()
      resolve()
    })
  })
}

function stopMockSseServer() {
  activeStream = null
  if (!mockServer) return
  const server = mockServer
  mockServer = null
  server.close()
  server.closeIdleConnections?.()
  server.closeAllConnections?.()
}

async function startViteServer() {
  const vitePath = resolve(process.cwd(), 'node_modules/vite/bin/vite.js')
  viteProcess = spawn(process.execPath, [vitePath, '--host', '127.0.0.1', '--port', '4175'], {
    cwd: process.cwd(),
    env: { ...process.env, VITE_API_BASE_URL: 'http://127.0.0.1:8001' },
    stdio: 'ignore',
    windowsHide: true
  })

  const startedAt = Date.now()
  while (Date.now() - startedAt < 30_000) {
    try {
      const response = await fetch('http://127.0.0.1:4175/')
      if (response.ok) return
    } catch {
      // Vite is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100))
  }
  throw new Error('Vite test server did not start within 30 seconds')
}

async function stopViteServer() {
  const serverProcess = viteProcess
  viteProcess = null
  if (!serverProcess || serverProcess.killed) return
  await new Promise((resolveStop) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      resolveStop()
    }
    serverProcess.once('exit', finish)
    serverProcess.kill()
    const forceStop = setTimeout(() => {
      serverProcess.kill('SIGKILL')
      finish()
    }, 2_000)
    forceStop.unref()
  })
}

test.beforeAll(async () => {
  await startMockSseServer()
  await startViteServer()
})
test.afterAll(async () => {
  stopMockSseServer()
  await stopViteServer()
})
test.beforeEach(() => {
  stopEndpointCalls = 0
})

async function authenticateAndMockPortal(page) {
  await page.addInitScript(() => localStorage.setItem('token', 'e2e-token'))
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path.endsWith('/ai-assistant/conversations/42/messages') || /\/ai-assistant\/messages\/\d+\/stop$/.test(path)) {
      return route.continue()
    }
    if (path.endsWith('/auth/me')) {
      return route.fulfill({ json: { id: 7, username: 'e2e', full_name: 'E2E', role: 'info_maintainer', is_superuser: true } })
    }
    if (path.endsWith('/portal/applications')) {
      return route.fulfill({ json: {
        code: 0,
        message: 'ok',
        data: [
          { code: 'investment', company_name: 'Investment Company', route: '/investment', status: 'construction', accessible: true },
          { code: 'supplymanagement', company_name: 'Supply Management Company', route: '/supplymanagement', status: 'online', accessible: true },
          { code: 'fundmanagement', company_name: 'Fund Management Company', route: '/fundmanagement', status: 'construction', accessible: true }
        ]
      } })
    }
    if (path.endsWith('/portal/me/permissions')) {
      return route.fulfill({ json: {
        code: 0,
        message: 'ok',
        data: { is_superuser: true, company_roles: { supplymanagement: 'info_maintainer' }, resources: ['supply.scenic.analytics'] }
      } })
    }
    if (path.endsWith('/ai-assistant/suggestions')) {
      return route.fulfill({ json: { code: 0, message: 'ok', data: ['What is this platform for?'] } })
    }
    if (path.endsWith('/ai-assistant/conversations') && request.method() === 'GET') {
      return route.fulfill({ json: { code: 0, message: 'ok', data: { items: [], total: 0, page: 1, size: 50 } } })
    }
    if (path.endsWith('/ai-assistant/conversations') && request.method() === 'POST') {
      const payload = request.postDataJSON() || {}
      return route.fulfill({ json: { code: 0, message: 'ok', data: conversation(payload.title || 'E2E conversation') } })
    }
    if (/\/ai-assistant\/conversations\/\d+$/.test(path)) {
      return route.fulfill({ json: { code: 0, message: 'ok', data: conversation() } })
    }
    return route.fulfill({ json: { code: 0, message: 'ok', data: {} } })
  })
}

test('desktop streams an answer and navigates only after action click', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await authenticateAndMockPortal(page)
  await page.goto('/')

  await expect(page.locator('[data-testid="assistant-region"]')).toBeVisible()
  await expect(page.locator('[data-testid="application-entry"]')).toHaveCount(3)
  await page.locator('#assistant-question').fill('Show Zunyi Zoo operating data')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible()
  await expect(page.getByText('The platform answer is ready.')).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: scenicAction.label })).toBeVisible()

  await page.getByRole('button', { name: scenicAction.label }).click()
  await expect(page).toHaveURL(/\/supplymanagement\/cultural-tourism\/zunyi-zoo$/)
})

test('mobile opens conversations, stops generation, and keeps business entries in viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticateAndMockPortal(page)
  await page.goto('/')
  await expect(page.locator('[data-testid="application-entry"]')).toHaveCount(3)

  await page.locator('.ai-workspace__drawer-button').click()
  await expect(page.locator('.el-drawer .conversation-sidebar')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.el-drawer .conversation-sidebar')).toBeHidden()
  await page.locator('#assistant-question').fill('stop this answer')
  await page.getByRole('button', { name: '发送问题' }).click()
  const stopButton = page.getByRole('button', { name: '停止生成' })
  await expect(stopButton).toBeVisible()
  await stopButton.click()
  await expect.poll(() => stopEndpointCalls).toBe(1)
  await expect(page.getByRole('button', { name: '发送问题' })).toBeVisible()

  const applications = page.locator('[data-testid="application-region"]')
  await applications.scrollIntoViewIfNeeded()
  await expect(applications).toBeVisible()
  const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth && document.body.scrollWidth <= window.innerWidth)
  expect(fitsViewport).toBe(true)
})
