import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const STORAGE_KEY = 'docmind-theme'
const MODES = [
  { value: 'auto', label: '跟随系统', icon: 'Operation' },
  { value: 'light', label: '浅色', icon: 'Sunny' },
  { value: 'dark', label: '深色', icon: 'Moon' },
]

function readMode() {
  try { return localStorage.getItem(STORAGE_KEY) || 'auto' } catch { return 'auto' }
}
function systemDark() {
  try { return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) } catch { return false }
}
/** 应用主题到 <html>：class="dark"（Element Plus 暗色变量）+ data-theme 属性 */
export function applyTheme(mode = readMode()) {
  const dark = mode === 'dark' || (mode === 'auto' && systemDark())
  const el = document.documentElement
  el.classList.toggle('dark', dark)
  el.setAttribute('data-theme', dark ? 'dark' : 'light')
  return dark
}

/** 主题状态：auto（跟随系统）/ light / dark，循环切换 */
export function useTheme() {
  const mode = ref(readMode())
  const isDark = ref(false)
  const meta = computed(() => MODES.find((m) => m.value === mode.value) || MODES[0])

  function setMode(next) {
    mode.value = next
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* 隐私模式等场景忽略 */ }
    isDark.value = applyTheme(next)
  }
  function cycle() {
    const i = MODES.findIndex((m) => m.value === mode.value)
    setMode(MODES[(i + 1) % MODES.length].value)
  }
  function onSystemChange() {
    if (mode.value === 'auto') isDark.value = applyTheme('auto')
  }
  onMounted(() => {
    isDark.value = applyTheme(mode.value)
    try { window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', onSystemChange) } catch { /* ignore */ }
  })
  onBeforeUnmount(() => {
    try { window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', onSystemChange) } catch { /* ignore */ }
  })
  return { mode, isDark, meta, setMode, cycle }
}
