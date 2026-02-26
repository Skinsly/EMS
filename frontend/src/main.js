import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './styles.css'
import './styles/sidebar.css'
import './styles/segment-title-fix.css'
import { registerSW } from 'virtual:pwa-register'
import { ElMessage } from 'element-plus'

let toastSeed = 1

const showFloatingToast = (type, options = {}) => {
  const normalized = typeof options === 'string' ? { message: options } : options
  const message = `${normalized.message || ''}`.trim()
  if (!message) {
    return { close: () => {} }
  }

  const id = `app-float-toast-${toastSeed++}`
  const duration = Number(normalized.duration ?? 2200)

  const el = document.createElement('div')
  el.id = id
  el.className = `app-float-toast app-float-toast-${type}`
  el.textContent = message
  document.body.appendChild(el)

  const close = () => {
    const target = document.getElementById(id)
    if (!target) return
    target.classList.add('is-hiding')
    window.setTimeout(() => {
      target.remove()
    }, 180)
  }

  window.setTimeout(close, Math.max(600, duration))
  return { close }
}

;['success', 'error', 'warning', 'info'].forEach((type) => {
  ElMessage[type] = (options = {}) => showFloatingToast(type, options)
})

registerSW({ immediate: true })

createApp(App).use(createPinia()).use(router).mount('#app')
