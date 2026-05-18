import ElementPlus, { ElMessageBox } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles/main.css'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')

let updatePromptVisible = false

function promptForAppUpdate() {
  if (updatePromptVisible) return
  updatePromptVisible = true

  ElMessageBox.confirm('检测到新版本，刷新后即可使用最新界面。', '应用已更新', {
    type: 'info',
    confirmButtonText: '立即刷新',
    cancelButtonText: '稍后',
    autofocus: false,
  })
    .then(() => window.location.reload())
    .catch(() => {})
    .finally(() => {
      updatePromptVisible = false
    })
}

function watchForServiceWorkerUpdate(registration: ServiceWorkerRegistration) {
  registration.addEventListener('updatefound', () => {
    const worker = registration.installing
    if (!worker) return

    worker.addEventListener('statechange', () => {
      if (worker.state === 'installed' && navigator.serviceWorker.controller) {
        promptForAppUpdate()
      }
    })
  })
}

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then((registration) => {
        watchForServiceWorkerUpdate(registration)
        registration.update().catch(() => {})
      })
      .catch((error) => {
        console.warn('Service worker registration failed', error)
      })
  })
}
