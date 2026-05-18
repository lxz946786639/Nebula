import { computed, readonly, ref, shallowRef } from 'vue'

type InstallOutcome = 'accepted' | 'dismissed'

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[]
  readonly userChoice: Promise<{ outcome: InstallOutcome; platform: string }>
  prompt(): Promise<void>
}

const installPrompt = shallowRef<BeforeInstallPromptEvent | null>(null)
const isStandalone = ref(false)
let initialized = false

function isIosStandalone() {
  return Boolean((window.navigator as Navigator & { standalone?: boolean }).standalone)
}

function readStandaloneState() {
  return window.matchMedia('(display-mode: standalone)').matches || isIosStandalone()
}

function initPwaInstallPrompt() {
  if (initialized || typeof window === 'undefined') return
  initialized = true

  const updateStandaloneState = () => {
    isStandalone.value = readStandaloneState()
    if (isStandalone.value) installPrompt.value = null
  }

  updateStandaloneState()

  const displayModeQuery = window.matchMedia('(display-mode: standalone)')
  if (displayModeQuery.addEventListener) {
    displayModeQuery.addEventListener('change', updateStandaloneState)
  } else {
    displayModeQuery.addListener(updateStandaloneState)
  }

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    updateStandaloneState()
    if (!isStandalone.value) {
      installPrompt.value = event as BeforeInstallPromptEvent
    }
  })

  window.addEventListener('appinstalled', () => {
    isStandalone.value = true
    installPrompt.value = null
  })
}

export function usePwaInstallPrompt() {
  initPwaInstallPrompt()

  async function promptInstall() {
    const promptEvent = installPrompt.value
    if (!promptEvent) return false

    installPrompt.value = null
    await promptEvent.prompt()
    const choice = await promptEvent.userChoice
    return choice.outcome === 'accepted'
  }

  return {
    canInstall: computed(() => Boolean(installPrompt.value) && !isStandalone.value),
    isStandalone: readonly(isStandalone),
    promptInstall,
  }
}
