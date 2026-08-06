import DOMPurify from 'dompurify'
import { marked, Renderer } from 'marked'

const ALLOWED_TAGS = [
  'p',
  'br',
  'strong',
  'em',
  'ul',
  'ol',
  'li',
  'blockquote',
  'code',
  'pre',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td'
]

const ACTION_KEYS = new Set(['type', 'scenic_id', 'label'])
const URL_TEXT_PATTERN = /\b(?:(?:(?:https?|ftp):\/\/|www\.)[a-z0-9._~:/?#@!$&'()*+,;=%-]+|mailto:[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+)/giu

function stripUrlText(value) {
  return String(value || '').replace(URL_TEXT_PATTERN, '')
}

function stripUrlTextFromHtml(html) {
  const template = document.createElement('template')
  template.innerHTML = html
  const pending = [...template.content.childNodes]
  while (pending.length) {
    const node = pending.pop()
    if (node.nodeType === 3) node.textContent = stripUrlText(node.textContent)
    else pending.push(...node.childNodes)
  }
  return template.innerHTML
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function createRestrictedRenderer() {
  const renderer = new Renderer()
  const defaultText = renderer.text
  renderer.html = () => ''
  renderer.image = () => ''
  renderer.hr = () => ''
  renderer.checkbox = () => ''
  renderer.code = ({ text }) => `<pre><code>${escapeHtml(text)}\n</code></pre>\n`
  renderer.heading = function heading({ tokens }) {
    return `<p>${this.parser.parseInline(tokens)}</p>\n`
  }
  renderer.del = function deleted({ tokens }) {
    return this.parser.parseInline(tokens)
  }
  renderer.link = function link({ text, tokens }) {
    if (!stripUrlText(text).trim()) return ''
    return this.parser.parseInline(tokens)
  }
  renderer.text = function text(token) {
    const scrubbed = stripUrlText(token.text)
    return defaultText.call(this, { ...token, raw: scrubbed, text: scrubbed })
  }
  renderer.list = function list(token) {
    const tag = token.ordered ? 'ol' : 'ul'
    const body = token.items.map((item) => this.listitem(item)).join('')
    return `<${tag}>\n${body}</${tag}>\n`
  }
  renderer.listitem = function listitem(item) {
    return `<li>${this.parser.parse(item.tokens)}</li>\n`
  }
  renderer.tablecell = function tablecell(token) {
    const tag = token.header ? 'th' : 'td'
    return `<${tag}>${this.parser.parseInline(token.tokens)}</${tag}>\n`
  }
  return renderer
}

export function renderSafeMarkdown(source) {
  const raw = marked.parse(String(source || ''), {
    gfm: true,
    breaks: true,
    renderer: createRestrictedRenderer()
  })
  if (DOMPurify.isSupported !== true || typeof DOMPurify.sanitize !== 'function') return ''
  const sanitized = DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [],
    ALLOW_ARIA_ATTR: false,
    ALLOW_DATA_ATTR: false,
    ALLOW_UNKNOWN_PROTOCOLS: false
  })
  return stripUrlTextFromHtml(sanitized)
}

export function validatedAction(action) {
  if (!action || typeof action !== 'object' || Array.isArray(action)) return null
  try {
    if (typeof structuredClone !== 'function') return null
    if (Object.getPrototypeOf(action) !== Object.prototype) return null
    const keys = Reflect.ownKeys(action)
    if (keys.length !== ACTION_KEYS.size || keys.some((key) => typeof key !== 'string' || !ACTION_KEYS.has(key))) {
      return null
    }
    const descriptors = Object.getOwnPropertyDescriptors(action)
    if (keys.some((key) => !Object.hasOwn(descriptors[key], 'value'))) return null
    const cloned = structuredClone(action)
    if (Object.getPrototypeOf(cloned) !== Object.prototype) return null
    const clonedDescriptors = Object.getOwnPropertyDescriptors(cloned)
    const snapshot = {
      type: clonedDescriptors.type.value,
      scenic_id: clonedDescriptors.scenic_id.value,
      label: clonedDescriptors.label.value
    }
    if (snapshot.type !== 'navigate_to_scenic') return null
    if (typeof snapshot.scenic_id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(snapshot.scenic_id)) return null
    if (typeof snapshot.label !== 'string') return null
    const label = snapshot.label.trim()
    if (!label || label.length > 80) return null
    return { type: snapshot.type, scenic_id: snapshot.scenic_id, label }
  } catch {
    return null
  }
}
