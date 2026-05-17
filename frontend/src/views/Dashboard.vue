<template>
  <div class="dashboard-page">
    <section class="surface dashboard-hero">
      <div>
        <span class="eyebrow">系统概览</span>
        <h2>运行状态</h2>
      </div>
      <el-button :icon="Refresh" :loading="loading" circle title="刷新概览" @click="load" />
    </section>

    <section class="dashboard-card-grid">
      <div class="stat-card">
        <span>订阅</span>
        <strong>{{ stats.subscriptions }}</strong>
      </div>
      <div class="stat-card">
        <span>启用</span>
        <strong>{{ stats.enabled_subscriptions }}</strong>
      </div>
      <div class="stat-card">
        <span>节点</span>
        <strong>{{ stats.nodes }}</strong>
      </div>
      <div class="stat-card">
        <span>智能代理</span>
        <strong>{{ stats.enabled_smart_proxies }}/{{ stats.smart_proxies }}</strong>
      </div>
      <div class="stat-card">
        <span>缓存键</span>
        <strong>{{ stats.cache_keys }}</strong>
      </div>
      <div class="stat-card">
        <span>总流量</span>
        <strong>{{ formatBytes(stats.traffic.total) }}</strong>
      </div>
      <div class="stat-card">
        <span>已用流量</span>
        <strong>{{ formatBytes(stats.traffic.used) }}</strong>
      </div>
      <div class="stat-card">
        <span>剩余流量</span>
        <strong>{{ formatBytes(stats.traffic.remaining) }}</strong>
      </div>
      <div class="stat-card">
        <span>最近到期</span>
        <strong class="compact-stat">{{ formatDateTime(stats.traffic.expire_at) }}</strong>
      </div>
    </section>

    <section class="dashboard-detail-grid">
      <section class="surface dashboard-status-card">
        <div class="toolbar">
          <h2>服务状态</h2>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Redis">
            <el-tag :type="statusTag(stats.redis_status)">{{ statusText(stats.redis_status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="subconverter">
            <el-tag :type="statusTag(stats.subconverter_status)">{{ statusText(stats.subconverter_status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Mihomo">
            <el-tag :type="statusTag(stats.mihomo_status)">{{ statusText(stats.mihomo_status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Mihomo 版本">{{ stats.mihomo_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最近更新">{{ formatDateTime(stats.last_updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="流量采集">{{ formatDateTime(stats.traffic.polled_at) }}</el-descriptions-item>
        </el-descriptions>
      </section>

      <section class="surface dashboard-subscription-panel">
        <div class="toolbar">
          <h2>客户端订阅地址</h2>
        </div>
        <div class="url-list">
          <div v-for="item in stats.client_subscriptions" :key="item.target" class="url-row">
            <div>
              <strong>{{ item.label }}</strong>
              <code>{{ fullUrl(item.path) }}</code>
            </div>
            <el-button :icon="DocumentCopy" circle title="复制订阅地址" @click="copy(fullUrl(item.path))" />
          </div>
        </div>
      </section>

      <section class="surface dashboard-subscription-panel">
        <div class="toolbar">
          <h2>代理地址列表</h2>
        </div>
        <div class="url-list">
          <div v-for="item in proxyAddresses" :key="item.id" class="url-row proxy-url-row">
            <div>
              <div class="proxy-url-title">
                <strong>{{ item.name }}</strong>
                <el-tag size="small" effect="plain">{{ proxyTypeLabel(item.proxy_type) }}</el-tag>
              </div>
              <code>{{ item.endpoint }}</code>
            </div>
            <el-button :icon="DocumentCopy" circle title="复制代理地址" @click="copy(item.endpoint)" />
          </div>
          <el-empty v-if="!proxyAddresses.length" description="暂无代理地址" :image-size="72" />
        </div>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { DocumentCopy, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import http from '@/api/http'
import { useStatusSocket } from '@/composables/useStatusSocket'
import { formatDateTime } from '@/utils/datetime'

interface ClientSubscription {
  label: string
  target: string
  path: string
}

interface ProxyAddress {
  id: number
  name: string
  proxy_type: string
  endpoint: string
}

const stats = reactive({
  subscriptions: 0,
  enabled_subscriptions: 0,
  nodes: 0,
  smart_proxies: 0,
  enabled_smart_proxies: 0,
  cache_keys: 0,
  redis_status: '-',
  subconverter_status: '-',
  mihomo_status: '-',
  mihomo_version: null as string | null,
  last_updated_at: '',
  traffic: {
    upload: 0,
    download: 0,
    used: 0,
    total: 0,
    remaining: 0,
    expire_at: null as string | null,
    polled_at: null as string | null,
    items: [],
  },
  client_subscriptions: [] as ClientSubscription[],
})
const proxyAddresses = ref<ProxyAddress[]>([])
const loading = ref(false)
const { connect: connectStatusSocket, stop: stopStatusSocket } = useStatusSocket((message) => {
  if (message.dashboard && typeof message.dashboard === 'object') {
    Object.assign(stats, message.dashboard)
  }
}, { topics: ['dashboard'], intervalMs: 15000 })

async function load() {
  loading.value = true
  try {
    const [{ data: dashboard }, { data: smartProxies }] = await Promise.all([
      http.get('/dashboard'),
      http.get('/smart-proxies'),
    ])
    Object.assign(stats, dashboard)
    proxyAddresses.value = smartProxies.map((item: ProxyAddress) => ({
      id: item.id,
      name: item.name,
      proxy_type: item.proxy_type,
      endpoint: item.endpoint,
    }))
  } finally {
    loading.value = false
  }
}

function formatBytes(value: number) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

function fullUrl(path: string) {
  return `${window.location.origin}${path}`
}

function normalizedStatus(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

function statusText(value?: string | null) {
  const status = normalizedStatus(value)
  const labels: Record<string, string> = {
    ok: '正常',
    healthy: '正常',
    online: '在线',
    running: '运行中',
    configured: '已配置',
    unavailable: '不可用',
    offline: '离线',
    failed: '异常',
    error: '异常',
    degraded: '异常',
    core_unavailable: '核心不可用',
    stopped: '已停止',
    unknown: '未知',
  }
  return labels[status] || '未知'
}

function statusTag(value?: string | null) {
  const status = normalizedStatus(value)
  if (['ok', 'healthy', 'online', 'running'].includes(status)) return 'success'
  if (['stopped', 'configured', 'unknown', ''].includes(status)) return 'info'
  if (['failed', 'error', 'degraded', 'core_unavailable'].includes(status)) return 'danger'
  return 'warning'
}

function proxyTypeLabel(value: string) {
  if (value === 'socks') return 'SOCKS5'
  if (value === 'mixed') return 'Mixed'
  return 'HTTP'
}

async function copy(value: string) {
  await navigator.clipboard.writeText(value)
  ElMessage.success('已复制')
}

onMounted(() => {
  load()
  connectStatusSocket()
})

onBeforeUnmount(() => {
  stopStatusSocket()
})
</script>
