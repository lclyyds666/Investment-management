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
  renderer.link = function link({ tokens }) {
    return this.parser.parseInline(tokens)
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
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [],
    ALLOW_ARIA_ATTR: false,
    ALLOW_DATA_ATTR: false,
    ALLOW_UNKNOWN_PROTOCOLS: false
  })
}

export function validatedAction(action) {
  if (!action || typeof action !== 'object' || Array.isArray(action)) return null
  const keys = Object.keys(action)
  if (keys.some((key) => !ACTION_KEYS.has(key))) return null
  if (action.type !== 'navigate_to_scenic') return null
  if (typeof action.scenic_id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(action.scenic_id)) return null
  if (typeof action.label !== 'string') return null
  const label = action.label.trim()
  if (!label || label.length > 80) return null
  return { type: action.type, scenic_id: action.scenic_id, label }
}
