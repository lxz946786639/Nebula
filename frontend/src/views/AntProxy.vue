<template>
  <section class="surface list-page ant-proxy-page">
    <div v-if="showSourceEntry" class="ant-entry">
      <div class="ant-entry-shell">
        <div class="ant-entry-heading">
          <div>
            <h2>蚂蚁代理</h2>
            <p>登录 Ant 账号或上传 ant.db</p>
          </div>
          <div v-if="status.loaded" class="ant-entry-actions">
            <el-button link type="primary" @click="cancelRelogin">已有登录数据，返回</el-button>
          </div>
        </div>

      <el-tabs
        v-model="sourceMode"
        class="ant-source-tabs ant-source-tabs--entry"
        :before-leave="beforeSourceModeLeave"
      >
        <el-tab-pane name="account">
          <template #label>
            <span>账号登录</span>
          </template>

          <div class="ant-source-card">
            <el-form class="ant-login-form" :model="loginForm" autocomplete="off" label-position="top" @submit.prevent>
              <div class="ant-login-grid">
                <el-form-item label="Ant 账号">
                  <el-input
                    v-model="loginForm.username"
                    autocomplete="new-password"
                    autocapitalize="off"
                    autocorrect="off"
                    clearable
                    data-1p-ignore="true"
                    data-form-type="other"
                    data-lpignore="true"
                    name="nebula-ant-account-field"
                    :prefix-icon="User"
                    placeholder="请输入账号"
                    spellcheck="false"
                  />
                </el-form-item>
                <el-form-item label="Ant 密码">
                  <el-input
                    v-model="loginForm.password"
                    autocomplete="new-password"
                    data-1p-ignore="true"
                    data-form-type="other"
                    data-lpignore="true"
                    name="nebula-ant-secret-field"
                    show-password
                    type="password"
                    :prefix-icon="Lock"
                    placeholder="请输入密码"
                    @keyup.enter="loginAnt"
                  />
                </el-form-item>
                <el-form-item label="客户端版本">
                  <el-select v-model="loginForm.appVersion" class="ant-version-select" name="nebula-ant-version-field">
                    <el-option v-for="version in appVersionOptions" :key="version" :label="version" :value="version" />
                  </el-select>
                </el-form-item>
              </div>
              <div class="ant-source-actions">
                <el-button class="ant-source-submit" type="primary" :icon="UserFilled" :loading="loginLoading" @click="loginAnt">
                  登录并同步
                </el-button>
              </div>
            </el-form>
          </div>
        </el-tab-pane>

        <el-tab-pane name="upload">
          <template #label>
            <span>上传 ant.db</span>
          </template>

          <div class="ant-source-card">
            <div class="ant-upload-settings">
              <span>客户端版本</span>
              <el-select v-model="loginForm.appVersion" class="ant-version-select" name="nebula-ant-upload-version-field">
                <el-option v-for="version in appVersionOptions" :key="version" :label="version" :value="version" />
              </el-select>
            </div>
            <el-upload
              class="ant-upload-drop"
              accept=".db,.msgpack"
              drag
              :http-request="uploadDb"
              :show-file-list="false"
            >
              <el-icon class="ant-upload-icon"><UploadFilled /></el-icon>
              <div class="ant-upload-text">拖拽 ant.db 到这里，或点击选择文件</div>
              <div class="ant-upload-tip">支持 ant.db / msgpack 文件，上传后会自动读取节点。</div>
            </el-upload>
          </div>
        </el-tab-pane>
      </el-tabs>
      </div>
    </div>

    <template v-else>
    <div class="toolbar ant-toolbar">
      <div class="toolbar-filters ant-toolbar-fields">
        <el-input v-model="listenHost" class="ant-host-input" placeholder="监听地址" />
        <el-input-number v-model="listenPort" :min="1" :max="65535" controls-position="right" />
        <el-input v-model="keyword" class="toolbar-filter-search" clearable placeholder="搜索节点" />
      </div>
      <div class="toolbar-actions">
        <el-button :icon="UserFilled" @click="beginRelogin">重新登录</el-button>
        <el-button v-if="canRefreshRemote" :icon="Refresh" :loading="refreshing" :disabled="loading" @click="refreshNodes()">刷新</el-button>
        <el-button v-if="status.running" type="warning" :icon="VideoPause" :loading="acting" @click="stopProxy">停止</el-button>
        <el-button v-else type="success" :icon="VideoPlay" :loading="acting" @click="startProxy()">启动</el-button>
        <el-button :icon="Aim" :loading="latencyLoading" @click="measureLatencies()">测速</el-button>
        <el-button :icon="Connection" :loading="testing" @click="testProxy">测试</el-button>
      </div>
    </div>

    <el-radio-group v-model="activeLine" class="ant-line-tabs" @change="loadNodesOnly">
      <el-radio-button label="free">免费专线 {{ status.free_node_count }}</el-radio-button>
      <el-radio-button label="paid">付费专线 {{ status.paid_node_count }}</el-radio-button>
    </el-radio-group>

    <el-descriptions class="desktop-summary ant-summary" :column="4" border>
      <el-descriptions-item label="登录状态">
        <el-tag :type="status.logged_in ? 'success' : 'warning'">{{ status.logged_in ? '已检测' : '未检测' }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="账号">{{ accountText }}</el-descriptions-item>
      <el-descriptions-item label="权益">{{ status.user.expire_description || '-' }}</el-descriptions-item>
      <el-descriptions-item label="节点">{{ lineSummary }}</el-descriptions-item>
      <el-descriptions-item label="登录方式">{{ loginMethodText }}</el-descriptions-item>
      <el-descriptions-item label="状态保存">
        <el-tag :type="status.persisted ? 'success' : 'warning'">{{ status.persisted ? '已持久化' : '未保存' }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="内置代理">
        <el-tag :type="status.running ? 'success' : 'info'">{{ status.running ? '运行中' : '已停止' }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="地址">
        <span class="endpoint-inline">
          {{ status.endpoint }}
          <el-button :icon="DocumentCopy" circle size="small" title="复制代理地址" @click="copy(status.endpoint)" />
        </span>
      </el-descriptions-item>
      <el-descriptions-item label="连接">{{ status.active_connections }} / {{ status.total_connections }}</el-descriptions-item>
      <el-descriptions-item label="流量">{{ formatBytes(status.upload_bytes) }} / {{ formatBytes(status.download_bytes) }}</el-descriptions-item>
    </el-descriptions>

    <div class="mobile-summary-grid">
      <div class="mobile-summary-item">
        <span>登录状态</span>
        <strong>{{ status.logged_in ? '已检测' : '未检测' }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>内置代理</span>
        <strong>{{ status.running ? '运行中' : '已停止' }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>节点</span>
        <strong>{{ status.node_count }}</strong>
      </div>
      <div class="mobile-summary-item">
        <span>连接</span>
        <strong>{{ status.active_connections }}</strong>
      </div>
    </div>

    <div class="ant-current">
      <div>
        <span>当前节点</span>
        <strong>{{ status.selected_node?.name || '-' }}</strong>
      </div>
      <div>
        <span>协议</span>
        <strong>{{ selectedTransport }}</strong>
      </div>
      <div>
        <span>远端</span>
        <strong>{{ selectedEndpoint }}</strong>
      </div>
      <div>
        <span>最近状态</span>
        <strong>{{ lastState }}</strong>
      </div>
    </div>

    <el-table class="list-table desktop-table" :data="filteredNodes" stripe height="100%" empty-text="暂无 Ant 节点">
      <el-table-column label="节点" min-width="190" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="node-name-cell">
            <el-tag v-if="row.selected" size="small" type="success" effect="plain">当前</el-tag>
            {{ row.name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="地区" min-width="130">
        <template #default="{ row }">{{ regionText(row) }}</template>
      </el-table-column>
      <el-table-column label="远端" min-width="160">
        <template #default="{ row }">{{ row.server }}:{{ row.port }}</template>
      </el-table-column>
      <el-table-column label="协议" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.tls ? 'success' : 'info'" effect="plain">{{ row.transport || 'tcp' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="在线" width="100">
        <template #default="{ row }">
          <span class="online-cell">{{ onlineText(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="延迟" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="latencyTag(row.latency_ms)" effect="plain">{{ latencyText(row.latency_ms) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="150">
        <template #default="{ row }">{{ row.line_label }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-space :size="6" wrap>
            <el-button link type="primary" :icon="Switch" :disabled="row.selected" @click="selectNode(row.id)">切换</el-button>
            <el-button link type="success" :icon="VideoPlay" @click="startProxy(row.id)">启用</el-button>
          </el-space>
        </template>
      </el-table-column>
    </el-table>

    <div class="mobile-card-list">
      <el-empty v-if="!filteredNodes.length" description="暂无 Ant 节点" :image-size="72" />
      <article v-for="node in filteredNodes" v-else :key="node.id" class="mobile-card">
        <div class="mobile-card-head">
          <div class="mobile-card-title">
            <strong>{{ node.name }}</strong>
            <span>{{ regionText(node) }} · {{ node.server }}:{{ node.port }}</span>
          </div>
          <el-tag :type="node.selected ? 'success' : 'info'" effect="plain">{{ node.selected ? '当前' : node.transport || 'tcp' }}</el-tag>
        </div>
        <dl class="mobile-kv">
          <div>
            <dt>加密</dt>
            <dd>{{ node.cipher }}</dd>
          </div>
          <div>
            <dt>在线</dt>
            <dd>{{ onlineText(node) }}</dd>
          </div>
          <div>
            <dt>延迟</dt>
            <dd>{{ latencyText(node.latency_ms) }}</dd>
          </div>
        </dl>
        <div class="mobile-card-actions">
          <el-button :icon="Switch" :disabled="node.selected" @click="selectNode(node.id)">切换</el-button>
          <el-button :icon="VideoPlay" type="success" @click="startProxy(node.id)">启用</el-button>
        </div>
      </article>
    </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { Aim, Connection, DocumentCopy, Lock, Refresh, Switch, UploadFilled, User, UserFilled, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import http from '@/api/http'
import { copyText } from '@/utils/clipboard'

interface AntProxyUser {
  logged_in: boolean
  oauth_id: string
  uuid: string
  bind_phone: string
  username: string
  aff_present: boolean
  vip_day: number
  expire_description: string
  is_sign: number
  website_url: string
  ip: string
}

interface AntProxyNode {
  id: string
  source: string
  group: string
  name: string
  city: string
  country: string
  country_code: string
  pay_type: string
  line_type: 'free' | 'paid'
  line_label: string
  online_connections: number | null
  status: number | null
  latency_ms: number | null
  server: string
  port: number
  cipher: string
  transport: string
  tls: boolean
  selected: boolean
}

interface AntProxyStatus {
  db_path: string
  db_exists: boolean
  db_filename: string
  source_type: string
  source_label: string
  client_id: string
  api_url: string
  app_version: string
  loaded: boolean
  logged_in: boolean
  user: AntProxyUser
  node_count: number
  free_node_count: number
  paid_node_count: number
  selected_node: AntProxyNode | null
  running: boolean
  listen_host: string
  listen_port: number
  endpoint: string
  active_connections: number
  total_connections: number
  upload_bytes: number
  download_bytes: number
  started_at: string | null
  last_loaded_at: string | null
  last_latency_tested_at: string | null
  persisted: boolean
  last_persisted_at: string | null
  last_error: string | null
}

const emptyUser: AntProxyUser = {
  logged_in: false,
  oauth_id: '',
  uuid: '',
  bind_phone: '',
  username: '',
  aff_present: false,
  vip_day: 0,
  expire_description: '',
  is_sign: 0,
  website_url: '',
  ip: '',
}

const status = reactive<AntProxyStatus>({
  db_path: '',
  db_exists: false,
  db_filename: '',
  source_type: 'none',
  source_label: '未加载',
  client_id: '',
  api_url: '',
  app_version: '2.0.9',
  loaded: false,
  logged_in: false,
  user: emptyUser,
  node_count: 0,
  free_node_count: 0,
  paid_node_count: 0,
  selected_node: null,
  running: false,
  listen_host: '127.0.0.1',
  listen_port: 18080,
  endpoint: 'socks5://127.0.0.1:18080',
  active_connections: 0,
  total_connections: 0,
  upload_bytes: 0,
  download_bytes: 0,
  started_at: null,
  last_loaded_at: null,
  last_latency_tested_at: null,
  persisted: false,
  last_persisted_at: null,
  last_error: null,
})

const nodes = ref<AntProxyNode[]>([])
const loading = ref(false)
const refreshing = ref(false)
const acting = ref(false)
const testing = ref(false)
const latencyLoading = ref(false)
const loginLoading = ref(false)
const uploadLoading = ref(false)
const reloginMode = ref(false)
const sourceMode = ref<'account' | 'upload'>('account')
const activeLine = ref<'free' | 'paid'>('free')
const keyword = ref('')
const listenHost = ref('127.0.0.1')
const listenPort = ref(18080)
const lastTest = ref('')
const autoRefreshed = ref(false)
let pollTimer = 0

const loginForm = reactive({
  username: '',
  password: '',
  appVersion: '2.0.9',
})

const appVersionOptions = ['2.0.9']
const showSourceEntry = computed(() => !status.loaded || reloginMode.value)
const canRefreshRemote = computed(() => status.loaded && status.source_type === 'account')

const filteredNodes = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return nodes.value
  return nodes.value.filter((node) =>
    [node.name, node.city, node.country, node.country_code, node.server, node.source, node.group]
      .join(' ')
      .toLowerCase()
      .includes(value),
  )
})

const selectedTransport = computed(() => {
  const node = status.selected_node
  if (!node) return '-'
  return `${node.transport || 'tcp'} / ${node.cipher}`
})

const selectedEndpoint = computed(() => {
  const node = status.selected_node
  if (!node) return '-'
  return `${node.server}:${node.port}`
})

const lastState = computed(() => lastTest.value || status.last_error || (status.running ? '代理运行中' : '待启动'))
const lineSummary = computed(() => {
  const current = activeLine.value === 'free' ? status.free_node_count : status.paid_node_count
  return `${current} / ${status.node_count}`
})
const loginMethodText = computed(() => {
  if (!status.loaded) return '未加载'
  if (status.source_type === 'account') return '账号登录'
  if (status.source_type === 'upload' || status.source_type === 'local') return 'ant.db登录'
  return 'ant.db登录'
})
const accountText = computed(() => status.user.bind_phone || status.user.username || status.user.oauth_id || '-')

function beforeSourceModeLeave() {
  if (loginLoading.value || uploadLoading.value) {
    ElMessage.warning('当前操作进行中，请稍后再切换来源')
    return false
  }
  return true
}

function applyStatus(next: AntProxyStatus) {
  Object.assign(status, next)
  status.user = next.user || emptyUser
  listenHost.value = next.listen_host || listenHost.value
  listenPort.value = next.listen_port || listenPort.value
  loginForm.appVersion = next.app_version || loginForm.appVersion
  if (reloginMode.value) return
  if (next.source_type === 'account') {
    sourceMode.value = 'account'
  } else if (next.source_type === 'upload' || next.source_type === 'local') {
    sourceMode.value = 'upload'
  }
}

function beginRelogin() {
  sourceMode.value = 'account'
  reloginMode.value = true
  lastTest.value = ''
}

async function cancelRelogin() {
  reloginMode.value = false
  await maybeAutoRefreshAccountNodes()
}

async function load() {
  loading.value = true
  try {
    const statusResponse = await http.get<AntProxyStatus>('/ant-proxy/status')
    applyStatus(statusResponse.data)
    if (statusResponse.data.loaded) {
      await loadNodesOnly()
    } else {
      nodes.value = []
    }
  } finally {
    loading.value = false
  }
}

async function refreshNodes(options: { silent?: boolean; refreshLatency?: boolean } = {}) {
  if (!canRefreshRemote.value) {
    if (!options.silent) ElMessage.info('ant.db登录的数据请重新上传 ant.db 后更新')
    return null
  }
  refreshing.value = true
  try {
    const response = await http.post<AntProxyStatus>('/ant-proxy/refresh', {})
    applyStatus(response.data)
    const nodeResponse = await loadNodesOnly()
    if (!options.silent) {
      ElMessage.success(`节点已刷新：免费 ${response.data.free_node_count}，付费 ${response.data.paid_node_count}`)
    }
    if (options.refreshLatency !== false) {
      void measureLatencies({ silent: true }).catch(() => undefined)
    }
    return nodeResponse
  } finally {
    refreshing.value = false
  }
}

async function maybeAutoRefreshAccountNodes() {
  if (autoRefreshed.value || reloginMode.value || !canRefreshRemote.value) return
  autoRefreshed.value = true
  try {
    await refreshNodes({ silent: true })
  } catch {
    autoRefreshed.value = false
  }
}

async function loginAnt() {
  if (!loginForm.username.trim() || !loginForm.password.trim()) {
    ElMessage.warning('请输入 Ant 账号和密码')
    return
  }
  loginLoading.value = true
  try {
    const response = await http.post<AntProxyStatus>('/ant-proxy/login', {
      username: loginForm.username.trim(),
      password: loginForm.password,
      app_version: loginForm.appVersion || '2.0.9',
    })
    applyStatus(response.data)
    let nodeResponse = await loadNodesOnly()
    reloginMode.value = false
    autoRefreshed.value = true
    try {
      nodeResponse = (await refreshNodes({ silent: true })) || nodeResponse
    } catch {
      ElMessage.warning('账号登录成功，节点刷新失败，可稍后点击刷新')
    }
    loginForm.password = ''
    ElMessage.success(`账号登录成功，已同步 ${nodeResponse.data.total} 个节点`)
  } finally {
    loginLoading.value = false
  }
}

async function uploadDb(options: UploadRequestOptions) {
  uploadLoading.value = true
  try {
    const form = new FormData()
    form.append('file', options.file)
    form.append('app_version', loginForm.appVersion || '2.0.9')
    const response = await http.post<AntProxyStatus>('/ant-proxy/upload', form)
    applyStatus(response.data)
    const nodeResponse = await loadNodesOnly()
    reloginMode.value = false
    autoRefreshed.value = false
    options.onSuccess?.(response.data)
    ElMessage.success(`已读取 ${nodeResponse.data.total} 个节点`)
  } catch (error) {
    throw error
  } finally {
    uploadLoading.value = false
  }
}

async function selectNode(nodeId: string) {
  acting.value = true
  try {
    const response = await http.post<AntProxyStatus>('/ant-proxy/select', { node_id: nodeId })
    applyStatus(response.data)
    await loadNodesOnly()
    ElMessage.success('已切换节点')
  } finally {
    acting.value = false
  }
}

async function startProxy(nodeId?: string) {
  acting.value = true
  try {
    const response = await http.post<AntProxyStatus>('/ant-proxy/start', {
      node_id: nodeId || status.selected_node?.id || null,
      listen_host: listenHost.value || '127.0.0.1',
      listen_port: listenPort.value || 18080,
    })
    applyStatus(response.data)
    await loadNodesOnly()
    ElMessage.success(`内置代理已启动：${response.data.endpoint}`)
  } finally {
    acting.value = false
  }
}

async function stopProxy() {
  acting.value = true
  try {
    const response = await http.post<AntProxyStatus>('/ant-proxy/stop')
    applyStatus(response.data)
    ElMessage.success('内置代理已停止')
  } finally {
    acting.value = false
  }
}

async function testProxy() {
  testing.value = true
  try {
    const response = await http.post<{ ok: boolean; status_code: number; first_line: string; elapsed_ms: number }>('/ant-proxy/test', {
      url: 'http://www.gstatic.com/generate_204',
      timeout: 15,
    })
    lastTest.value = `${response.data.first_line || response.data.status_code} · ${response.data.elapsed_ms}ms`
    ElMessage.success(`测试通过：${lastTest.value}`)
  } finally {
    testing.value = false
  }
}

async function loadNodesOnly() {
  const nodeResponse = await http.get<{ total: number; items: AntProxyNode[] }>('/ant-proxy/nodes', {
    params: { line_type: activeLine.value },
  })
  nodes.value = nodeResponse.data.items
  return nodeResponse
}

async function measureLatencies(options: { silent?: boolean } = {}) {
  latencyLoading.value = true
  const lineType = activeLine.value
  try {
    const response = await http.post<{ total: number; online: number; failed: number; elapsed_ms: number; items: AntProxyNode[] }>(
      '/ant-proxy/latencies',
      {
        line_type: lineType,
        timeout_ms: 5000,
        concurrency: 20,
      },
    )
    if (activeLine.value === lineType) {
      nodes.value = response.data.items
    }
    if (!options.silent) {
      ElMessage.success(`测速完成：在线 ${response.data.online} / ${response.data.total}`)
    }
  } finally {
    latencyLoading.value = false
  }
}

async function copy(value: string) {
  if (!value) return
  await copyText(value)
  ElMessage.success('已复制')
}

function regionText(node: AntProxyNode) {
  return node.city || node.country || node.country_code || '-'
}

function onlineText(node: AntProxyNode) {
  return node.online_connections === null || node.online_connections === undefined ? '-' : `${node.online_connections} 人`
}

function latencyText(value: number | null) {
  return value === null || value === undefined ? '-' : `${value} ms`
}

function latencyTag(value: number | null) {
  if (value === null || value === undefined) return 'info'
  if (value < 300) return 'success'
  if (value < 500) return 'warning'
  return 'danger'
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`
}

onMounted(async () => {
  await load()
  await maybeAutoRefreshAccountNodes()
  pollTimer = window.setInterval(() => {
    if (status.running) load()
  }, 5000)
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.ant-proxy-page {
  gap: 12px;
}

.ant-entry {
  display: grid;
  min-height: min(620px, calc(100vh - 170px));
  align-items: center;
  padding: 20px 0;
}

.ant-entry-shell {
  width: min(760px, 100%);
  margin: 0 auto;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
  padding: 22px;
}

.ant-entry-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 18px;
}

.ant-entry-heading h2 {
  margin: 0;
  color: var(--heading);
  font-size: 22px;
  font-weight: 700;
  line-height: 1.25;
}

.ant-entry-heading p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.ant-entry-actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.ant-source-tabs {
  width: 100%;
}

.ant-source-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-radius: var(--radius);
  background: var(--panel-soft);
  padding: 4px;
}

.ant-source-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.ant-source-tabs :deep(.el-tabs__nav) {
  display: grid;
  width: 100%;
  min-width: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  float: none;
  gap: 4px;
}

.ant-source-tabs--entry :deep(.el-tabs__item) {
  align-items: center;
  justify-content: center;
  height: 40px;
  border: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
  border-radius: calc(var(--radius) - 2px);
  padding: 0 18px;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  line-height: 40px;
  transition:
    background-color 0.16s ease,
    color 0.16s ease,
    box-shadow 0.16s ease;
}

.ant-source-tabs--entry :deep(.el-tabs__item:hover) {
  border-color: color-mix(in srgb, var(--el-color-primary) 38%, var(--line));
  color: var(--heading);
}

.ant-source-tabs--entry :deep(.el-tabs__item.is-active) {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: #fff;
  box-shadow: 0 8px 18px rgb(20 184 166 / 18%);
}

.ant-source-tabs--entry :deep(.el-tabs__active-bar) {
  display: none;
}

.ant-source-card {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.ant-login-form {
  margin: 0;
}

.ant-login-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  align-items: end;
}

.ant-login-form :deep(.el-form-item) {
  margin: 0;
}

.ant-version-select {
  width: 100%;
}

.ant-upload-settings {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}

.ant-upload-settings span {
  color: var(--heading);
  font-size: 13px;
  font-weight: 700;
}

.ant-upload-settings .ant-version-select {
  width: 120px;
}

.ant-source-actions {
  display: flex;
  justify-content: stretch;
  margin-top: 14px;
}

.ant-source-submit {
  width: 100%;
  min-width: 138px;
}

.ant-upload-drop {
  width: 100%;
}

.ant-upload-drop :deep(.el-upload) {
  width: 100%;
}

.ant-upload-drop :deep(.el-upload-dragger) {
  width: 100%;
  padding: 34px 18px;
  border-color: var(--line);
  background: var(--panel-soft);
}

.ant-upload-drop :deep(.el-upload-dragger:hover) {
  border-color: var(--el-color-primary);
}

.ant-upload-icon {
  margin-bottom: 8px;
  color: var(--el-color-primary);
  font-size: 28px;
}

.ant-upload-text {
  color: var(--heading);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}

.ant-upload-tip {
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.ant-toolbar {
  margin-bottom: 0;
}

.ant-toolbar-fields {
  flex: 1 1 560px;
}

.ant-host-input {
  width: 150px;
}

.ant-summary {
  flex: 0 0 auto;
}

.ant-line-tabs {
  flex: 0 0 auto;
}

.ant-line-tabs :deep(.el-radio-button__inner) {
  min-width: 128px;
}

.endpoint-inline {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.ant-current {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  flex: 0 0 auto;
}

.ant-current > div {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel-soft);
  padding: 10px;
}

.ant-current span,
.ant-current strong {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ant-current span {
  color: var(--muted);
  font-size: 12px;
}

.ant-current strong {
  margin-top: 4px;
  color: var(--heading);
  font-size: 14px;
}

.node-name-cell {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 6px;
}

.online-cell {
  color: #22d3ee;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 860px) {
  .ant-entry {
    min-height: auto;
    align-items: start;
    padding: 4px 0;
  }

  .ant-entry-shell {
    padding: 16px;
  }

  .ant-entry-heading {
    align-items: center;
  }

  .ant-entry-actions {
    justify-content: flex-end;
  }

  .ant-login-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .ant-source-actions {
    justify-content: stretch;
  }

  .ant-source-submit {
    width: 100%;
  }

  .ant-upload-settings {
    align-items: stretch;
    flex-direction: column;
    gap: 6px;
  }

  .ant-upload-settings .ant-version-select {
    width: 100%;
  }

  .ant-current {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ant-host-input {
    width: 100%;
  }
}
</style>
