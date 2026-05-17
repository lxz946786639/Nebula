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
      <nav>
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
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
        <div class="sidebar-version">
          <span>版本号</span>
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
          <ThemeToggle placement="bottom" label="主题" />
          <div class="ws-status" :class="`is-${socketStatus}`" :title="socketTitle">
            <span class="ws-status-dot"></span>
            <span>{{ socketLabel }}</span>
          </div>
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
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ThemeToggle from '@/components/ThemeToggle.vue'
import { useStatusSocket } from '@/composables/useStatusSocket'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const appVersion = __APP_VERSION__
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

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(connectSocket)
onBeforeUnmount(stopSocket)
</script>
