# AI Assistant UUID Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent AI assistant submissions from failing when `crypto.randomUUID()` is unavailable while preserving valid UUID v4 values and existing retry idempotency.

**Architecture:** Add a focused frontend UUID utility that chooses the strongest available browser capability at call time, then replace the store's direct Web Crypto call with that utility. Keep the backend contract and retry state unchanged.

**Tech Stack:** Vue 3, Pinia, JavaScript ES modules, Vitest, Vite.

## Global Constraints

- Do not add an npm dependency.
- Return an RFC 4122 UUID v4 string on every path.
- Preserve same-content retry reuse of `client_message_id`.
- Do not modify backend APIs, database models, SSE behavior, or deployment configuration.
- Do not create a git commit unless the user explicitly requests one.

---

### Task 1: Add UUID compatibility utility and wire the assistant store

**Files:**
- Create: `frontend/src/utils/uuid.js`
- Create: `frontend/src/utils/uuid.test.js`
- Modify: `frontend/src/store/aiAssistant.js:1-4,254-259`
- Verify: `frontend/src/store/aiAssistant.test.js`

**Interfaces:**
- Produces: `createUuid(): string`, returning a valid UUID v4.
- Consumes: `globalThis.crypto.randomUUID`, `globalThis.crypto.getRandomValues`, `Date.now`, `performance.now`, and `Math.random` in decreasing preference order.
- Store contract: `sendMessage(conversationId, content)` continues to store and reuse the generated string as `client_message_id`.

- [x] **Step 1: Write failing UUID utility tests**

```javascript
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUuid } from './uuid'

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('createUuid', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('uses crypto.randomUUID when available', () => {
    const randomUUID = vi.fn(() => '11111111-1111-4111-8111-111111111111')
    vi.stubGlobal('crypto', { randomUUID })

    expect(createUuid()).toBe('11111111-1111-4111-8111-111111111111')
    expect(randomUUID).toHaveBeenCalledTimes(1)
  })

  it('formats getRandomValues bytes as UUID v4', () => {
    const getRandomValues = vi.fn((bytes) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index))
      return bytes
    })
    vi.stubGlobal('crypto', { getRandomValues })

    expect(createUuid()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
  })

  it('returns UUID v4 without Web Crypto', () => {
    vi.stubGlobal('crypto', undefined)
    vi.spyOn(Date, 'now').mockReturnValue(1723250000000)
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    expect(createUuid()).toMatch(UUID_V4_PATTERN)
  })
})
```

- [x] **Step 2: Run the test and verify the missing module failure**

Run: `npm test -- --run src/utils/uuid.test.js`

Expected: FAIL because `frontend/src/utils/uuid.js` does not exist.

- [x] **Step 3: Implement the UUID utility**

```javascript
function formatUuid(bytes) {
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join('')
  ].join('-')
}

function fillFallbackBytes(bytes) {
  let timestamp = Date.now()
  let highResolution = Math.floor((globalThis.performance?.now?.() || 0) * 1000)
  for (let index = 0; index < bytes.length; index += 1) {
    const source = index < 8 ? timestamp : highResolution
    bytes[index] = Math.floor(Math.random() * 256) ^ (source & 0xff)
    if (index < 8) timestamp = Math.floor(timestamp / 256)
    else highResolution = Math.floor(highResolution / 256)
  }
}

export function createUuid() {
  const cryptoObject = globalThis.crypto
  if (typeof cryptoObject?.randomUUID === 'function') {
    return cryptoObject.randomUUID()
  }

  const bytes = new Uint8Array(16)
  if (typeof cryptoObject?.getRandomValues === 'function') {
    cryptoObject.getRandomValues(bytes)
  } else {
    fillFallbackBytes(bytes)
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  return formatUuid(bytes)
}
```

- [x] **Step 4: Run UUID tests and verify all paths pass**

Run: `npm test -- --run src/utils/uuid.test.js`

Expected: 3 tests PASS.

- [x] **Step 5: Replace the direct store call**

Add the import:

```javascript
import { createUuid } from '@/utils/uuid'
```

Replace:

```javascript
: crypto.randomUUID()
```

with:

```javascript
: createUuid()
```

- [x] **Step 6: Run assistant store regression tests**

Run: `npm test -- --run src/store/aiAssistant.test.js`

Expected: all existing store tests PASS, including same-prompt retry ID reuse and new-prompt ID regeneration.

- [x] **Step 7: Run focused tests together**

Run: `npm test -- --run src/utils/uuid.test.js src/store/aiAssistant.test.js`

Expected: all focused tests PASS.

- [x] **Step 8: Build the production frontend**

Run: `npm run build`

Expected: Vite production build exits with code 0 and emits `frontend/dist`.

- [x] **Step 9: Review the final diff**

Run: `git diff --check && git diff -- frontend/src/utils/uuid.js frontend/src/utils/uuid.test.js frontend/src/store/aiAssistant.js`

Expected: no whitespace errors; only the UUID utility, tests, and store import/call change appear.
