import { computed, readonly, ref } from 'vue'

type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'nebula-theme'
const theme = ref<ThemeMode>('dark')
let initialized = false

function readStoredTheme(): ThemeMode | null {
  if (typeof window === 'undefined') return null
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'dark' || stored === 'light' ? stored : null
}

function getDefaultTheme(): ThemeMode {
  return 'dark'
}

function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  root.dataset.theme = mode
  root.classList.toggle('dark', mode === 'dark')
  root.classList.toggle('light', mode === 'light')
}

function setTheme(mode: ThemeMode, persist = true) {
  theme.value = mode
  applyTheme(mode)

  if (persist && typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, mode)
  }
}

function initTheme() {
  if (initialized) return
  initialized = true

  setTheme(readStoredTheme() ?? getDefaultTheme(), false)
}

export function useTheme() {
  initTheme()

  const isDark = computed(() => theme.value === 'dark')

  function toggleTheme() {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  return {
    theme: readonly(theme),
    isDark,
    setTheme,
    toggleTheme,
  }
}
