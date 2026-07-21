import { defineStore } from 'pinia'
import { ref } from 'vue'

// 主题模式（明亮/暗黑）全局状态 + localStorage 持久化。
// Element Plus 暗色靠 <html class="dark"> 触发（已在 main.js 引入 dark/css-vars.css）；
// 本 store 是「唯一开关」:切换 mode → 同步 html.dark 类 → 写回 localStorage。
// 等价于 antd 的 ConfigProvider + theme.defaultAlgorithm/darkAlgorithm,只是落到 EP 的类机制上。
const STORAGE_KEY = 'theme_mode'

// 读取持久化值;首次访问无记录时默认沿用旧版观感 = 暗色。
function readInitial() {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'light' || saved === 'dark' ? saved : 'dark'
}

// 把当前模式落到 <html> 上（EP 暗色变量随 .dark 生效）。
function applyToDom(mode) {
  const el = document.documentElement
  if (mode === 'dark') el.classList.add('dark')
  else el.classList.remove('dark')
  // color-scheme 让原生控件(滚动条/表单)也跟随明暗
  el.style.colorScheme = mode
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref(readInitial())

  // 应用到 DOM 并持久化。
  function apply() {
    applyToDom(mode.value)
    localStorage.setItem(STORAGE_KEY, mode.value)
  }

  // 供 main.js 在挂载前调用:按持久化值把 html.dark 就位,避免刷新闪烁。
  function init() {
    apply()
  }

  function setMode(next) {
    mode.value = next === 'light' ? 'light' : 'dark'
    apply()
  }

  function toggle() {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  return { mode, init, setMode, toggle }
})
