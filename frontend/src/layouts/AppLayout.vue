<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">N</div>
        <div>
          <strong>Nebula</strong>
          <span>Sub Hub</span>
        </div>
      </div>
      <div class="nav-shell" :class="{ 'has-left': canScrollNavLeft, 'has-right': canScrollNavRight }">
        <button
          class="nav-scroll-button nav-scroll-button-left"
          :class="{ 'is-visible': canScrollNavLeft }"
          type="button"
          aria-label="向左查看更多导航"
          :aria-hidden="!canScrollNavLeft"
          :tabindex="canScrollNavLeft ? 0 : -1"
          @click="scrollNav('left')"
        >
          <ArrowLeft />
        </button>
        <nav ref="navRef" @scroll.passive="updateNavScrollState">
          <RouterLink v-for="item in navItems" :key="item.path" :to="item.path">
            <component :is="item.icon" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <button
          class="nav-scroll-button nav-scroll-button-right"
          :class="{ 'is-visible': canScrollNavRight }"
          type="button"
          aria-label="向右查看更多导航"
          :aria-hidden="!canScrollNavRight"
          :tabindex="canScrollNavRight ? 0 : -1"
          @click="scrollNav('right')"
        >
          <ArrowRight />
        </button>
      </div>
      <div class="sidebar-actions">
        <div class="sidebar-user">
          <div class="sidebar-avatar">{{ userInitials }}</div>
          <div class="sidebar-user-meta">
            <strong>{{ username }}</strong>
            <span>管理员</span>
          </div>
        </div>
        <div class="sidebar-action-icons">
          <el-tooltip content="退出登录" placement="top" :show-after="250">
            <el-button :icon="SwitchButton" circle title="退出登录" aria-label="退出登录" @click="logout" />
          </el-tooltip>
        </div>
      </div>
      <div class="sidebar-footer">
        <div class="sidebar-version" :title="`当前版本 v${appVersion}`">
          <span>版本</span>
          <strong>v{{ appVersion }}</strong>
        </div>
      </div>
    </aside>
    <main class="main-panel">
      <header class="topbar">
        <div>
          <span class="eyebrow">Workspace</span>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-actions">
          <PwaInstallButton placement="bottom" />
          <ThemeToggle placement="bottom" label="主题" />
          <div class="ws-status" :class="`is-${socketStatus}`" :title="socketTitle">
            <span class="ws-status-dot"></span>
            <span>{{ socketLabel }}</span>
          </div>
          <el-button class="topbar-logout" :icon="SwitchButton" circle title="退出登录" aria-label="退出登录" @click="logout" />
        </div>
      </header>
      <section class="content-panel">
        <router-view />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft,
  ArrowRight,
  Collection,
  Connection,
  DataAnalysis,
  Document,
  Files,
  Guide,
  Monitor,
  SwitchButton,
  Tools,
} from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PwaInstallButton from '@/components/PwaInstallButton.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useStatusSocket } from '@/composables/useStatusSocket'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const appVersion = typeof __APP_VERSION__ === 'string' && __APP_VERSION__ ? __APP_VERSION__ : '1.1.0'
const navRef = ref<HTMLElement | null>(null)
const canScrollNavLeft = ref(false)
const canScrollNavRight = ref(false)
let navMeasureFrame = 0
let navActiveScrollTimer = 0
const { status: socketStatus, connect: connectSocket, stop: stopSocket } = useStatusSocket(() => {}, {
  topics: ['dashboard'],
  intervalMs: 30000,
})

const navItems = [
  { path: '/dashboard', label: '首页', icon: DataAnalysis },
  { path: '/subscriptions', label: '订阅管理', icon: Collection },
  { path: '/nodes', label: '节点管理', icon: Connection },
  { path: '/smart-proxies', label: '智能代理', icon: Guide },
  { path: '/rules', label: '规则管理', icon: Files },
  { path: '/templates', label: '配置模板', icon: Document },
  { path: '/settings', label: '系统设置', icon: Tools },
  { path: '/logs', label: '日志中心', icon: Monitor },
]

const title = computed(() => navItems.find((item) => item.path === route.path)?.label || '首页')
const username = computed(() => auth.username || 'admin')
const userInitials = computed(() => {
  const value = username.value.trim()
  if (!value) return 'AD'
  const letters = value.replace(/[^a-z0-9]/gi, '').slice(0, 2)
  return (letters || value.slice(0, 2)).toUpperCase()
})
const socketLabel = computed(() => {
  const labels: Record<typeof socketStatus.value, string> = {
    idle: '实时状态待连接',
    connecting: '实时状态连接中',
    connected: '实时状态正常',
    reconnecting: '实时状态重连中',
    disconnected: '实时状态已断开',
  }
  return labels[socketStatus.value]
})
const socketTitle = computed(() => `WebSocket：${socketLabel.value}`)

function measureNavScrollState() {
  const nav = navRef.value
  if (!nav) {
    canScrollNavLeft.value = false
    canScrollNavRight.value = false
    return
  }

  const maxScrollLeft = nav.scrollWidth - nav.clientWidth
  const threshold = 2
  canScrollNavLeft.value = nav.scrollLeft > threshold
  canScrollNavRight.value = maxScrollLeft > threshold && nav.scrollLeft < maxScrollLeft - threshold
}

function updateNavScrollState() {
  if (navMeasureFrame) cancelAnimationFrame(navMeasureFrame)
  navMeasureFrame = requestAnimationFrame(() => {
    navMeasureFrame = 0
    measureNavScrollState()
  })
}

function scrollToActiveNavItem(behavior: ScrollBehavior) {
  const nav = navRef.value
  const activeItem = nav?.querySelector<HTMLElement>('a.router-link-active')
  if (!nav || !activeItem) return

  const maxScrollLeft = Math.max(0, nav.scrollWidth - nav.clientWidth)
  const targetLeft = activeItem.offsetLeft - Math.max(0, (nav.clientWidth - activeItem.offsetWidth) / 2)
  const nextScrollLeft = Math.min(maxScrollLeft, Math.max(0, targetLeft))
  if (behavior === 'auto') {
    nav.scrollLeft = nextScrollLeft
    return
  }

  nav.scrollBy({
    left: nextScrollLeft - nav.scrollLeft,
    behavior,
  })
}

function scrollActiveNavIntoView(behavior: ScrollBehavior = 'smooth') {
  if (navActiveScrollTimer) window.clearTimeout(navActiveScrollTimer)

  const align = (attempt: number) => {
    measureNavScrollState()
    nextTick(() => {
      scrollToActiveNavItem(attempt === 0 ? behavior : 'auto')
      updateNavScrollState()

      if (attempt >= 3) {
        navActiveScrollTimer = 0
        return
      }

      navActiveScrollTimer = window.setTimeout(() => align(attempt + 1), attempt === 0 ? 140 : 100)
    })
  }

  align(0)
}

function scrollNav(direction: 'left' | 'right') {
  const nav = navRef.value
  if (!nav) return

  const distance = Math.max(144, Math.round(nav.clientWidth * 0.72))
  nav.scrollBy({
    left: direction === 'left' ? -distance : distance,
    behavior: 'smooth',
  })
  window.setTimeout(updateNavScrollState, 260)
}

async function logout() {
  try {
    await ElMessageBox.confirm('确认退出当前账号吗？退出后需要重新登录才能继续使用系统。', '退出登录', {
      type: 'warning',
      confirmButtonText: '退出登录',
      cancelButtonText: '取消',
      autofocus: false,
    })
  } catch {
    return
  }

  await auth.logout()
  stopSocket()
  router.push('/login')
}

watch(
  () => route.path,
  () => {
    nextTick(() => scrollActiveNavIntoView())
  },
)

onMounted(() => {
  connectSocket()
  window.addEventListener('resize', updateNavScrollState)
  nextTick(() => scrollActiveNavIntoView('auto'))
})

onBeforeUnmount(() => {
  stopSocket()
  window.removeEventListener('resize', updateNavScrollState)
  if (navMeasureFrame) cancelAnimationFrame(navMeasureFrame)
  if (navActiveScrollTimer) window.clearTimeout(navActiveScrollTimer)
})
</script>
