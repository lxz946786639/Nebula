<template>
  <section class="surface list-page">
    <div class="toolbar">
      <el-input v-model="group" placeholder="分组" clearable style="max-width: 220px" @change="load" />
      <div style="display: flex; gap: 10px">
        <el-button :icon="Setting" :loading="settingsLoading" @click="openSubscriptionSettings">订阅配置</el-button>
        <el-button :icon="Refresh" :loading="trafficRefreshing" @click="refreshTraffic">刷新流量</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增订阅</el-button>
      </div>
    </div>
    <el-table class="list-table" :data="items" stripe height="100%">
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="group_name" label="分组" width="120" />
      <el-table-column prop="priority" label="优先级" width="90" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新状态" width="130">
        <template #default="{ row }">
          <el-tooltip v-if="row.last_error" :content="row.last_error" placement="top">
            <el-tag :type="statusTag(row.last_status)">{{ statusText(row.last_status) }}</el-tag>
          </el-tooltip>
          <el-tag v-else :type="statusTag(row.last_status)">{{ statusText(row.last_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="流量使用" min-width="220">
        <template #default="{ row }">
          <div style="display: flex; flex-direction: column; gap: 6px">
            <span>{{ formatBytes(row.traffic_used) }} / {{ formatBytes(row.traffic_total) }}</span>
            <el-progress :percentage="trafficPercent(row)" :stroke-width="6" :show-text="false" />
            <div style="display: flex; gap: 6px; align-items: center">
              <small>剩余 {{ formatBytes(row.traffic_remaining) }}</small>
              <el-tooltip v-if="row.traffic_error" :content="row.traffic_error" placement="top">
                <el-tag size="small" :type="row.traffic_stale ? 'warning' : 'danger'" effect="plain">
                  {{ row.traffic_stale ? '异常保留' : '异常' }}
                </el-tag>
              </el-tooltip>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="到期时间" width="130">
        <template #default="{ row }">{{ formatDate(row.traffic_expire_at) }}</template>
      </el-table-column>
      <el-table-column label="最近更新时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.last_updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button :icon="Refresh" circle title="刷新订阅" @click="refresh(row.id)" />
          <el-button :icon="Edit" circle title="编辑订阅" @click="openEdit(row)" />
          <el-button :icon="Delete" circle title="删除订阅" type="danger" @click="remove(row.id)" />
        </template>
      </el-table-column>
    </el-table>
  </section>

  <el-dialog v-model="dialogVisible" :title="editingId ? '编辑订阅' : '新增订阅'" width="620px">
    <el-form label-position="top">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="URL"><el-input v-model="form.url" /></el-form-item>
      <el-form-item label="分组"><el-input v-model="form.group_name" /></el-form-item>
      <el-form-item label="标签">
        <el-select v-model="form.tags" multiple filterable allow-create default-first-option style="width: 100%" />
      </el-form-item>
      <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="0" /></el-form-item>
      <el-form-item label="更新间隔秒"><el-input-number v-model="form.update_interval" :min="60" /></el-form-item>
      <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="settingsDialogVisible" title="订阅配置" width="620px">
    <el-form v-loading="settingsLoading" label-position="top">
      <el-form-item v-for="item in subscriptionSettings" :key="item.key" :label="settingLabel(item.key)">
        <el-input
          v-model="subscriptionValues[item.key]"
          :type="item.secret ? 'password' : 'text'"
          :placeholder="settingPlaceholder(item.key)"
          :show-password="item.secret"
        />
        <small>{{ settingDescription(item) }}</small>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="settingsDialogVisible = false">取消</el-button>
      <el-button :icon="Refresh" :loading="settingsLoading" @click="loadSubscriptionSettings">刷新</el-button>
      <el-button type="primary" :icon="Check" :loading="settingsSaving" @click="saveSubscriptionSettings">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Check, Delete, Edit, Plus, Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import http from '@/api/http'

interface Subscription {
  id: number
  name: string
  url: string
  enabled: boolean
  tags: string[]
  group_name: string
  remark?: string
  update_interval: number
  priority: number
  last_status?: string
  last_error?: string | null
  last_updated_at?: string | null
  traffic_used: number
  traffic_total: number
  traffic_remaining: number
  traffic_expire_at?: string | null
  traffic_stale?: boolean
  traffic_error?: string | null
}

interface SettingItem {
  key: string
  value: string | null
  secret: boolean
  description?: string
}

const subscriptionSettingMeta: Record<string, { label: string; description: string; placeholder?: string }> = {
  subscription_token: {
    label: '订阅访问 Token',
    description: '客户端订阅地址使用的访问令牌，修改后客户端订阅 URL 中的 token 需要同步更新。',
    placeholder: '请输入订阅访问 Token',
  },
  cache_ttl_seconds: {
    label: '订阅缓存有效期（秒）',
    description: '生成后的客户端订阅内容缓存时间，单位为秒。',
    placeholder: '600',
  },
  traffic_poll_interval_minutes: {
    label: '流量轮询频率（分钟）',
    description: '后台自动采集订阅流量的间隔，填 0 表示关闭自动采集。',
    placeholder: '30',
  },
}

const items = ref<Subscription[]>([])
const subscriptionSettings = ref<SettingItem[]>([])
const subscriptionValues = reactive<Record<string, string | null>>({})
const group = ref('')
const trafficRefreshing = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settingsDialogVisible = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  url: '',
  enabled: true,
  tags: [] as string[],
  group_name: 'default',
  remark: '',
  update_interval: 3600,
  priority: 100,
})

async function load() {
  const { data } = await http.get('/subscriptions', { params: { group: group.value || undefined } })
  items.value = data
}

async function loadSubscriptionSettings() {
  settingsLoading.value = true
  try {
    const { data } = await http.get<SettingItem[]>('/settings', { params: { scope: 'subscription' } })
    subscriptionSettings.value = data
    for (const item of data) subscriptionValues[item.key] = item.value
  } finally {
    settingsLoading.value = false
  }
}

async function openSubscriptionSettings() {
  settingsDialogVisible.value = true
  if (!subscriptionSettings.value.length) await loadSubscriptionSettings()
}

async function saveSubscriptionSettings() {
  settingsSaving.value = true
  try {
    const settings: Record<string, string | null> = {}
    for (const item of subscriptionSettings.value) settings[item.key] = subscriptionValues[item.key]
    await http.put('/settings', { settings })
    ElMessage.success('订阅配置已保存')
    await loadSubscriptionSettings()
  } finally {
    settingsSaving.value = false
  }
}

function settingLabel(key: string) {
  return subscriptionSettingMeta[key]?.label || key
}

function settingDescription(item: SettingItem) {
  return subscriptionSettingMeta[item.key]?.description || item.description || ''
}

function settingPlaceholder(key: string) {
  return subscriptionSettingMeta[key]?.placeholder || ''
}

function reloadSoon() {
  window.setTimeout(() => {
    void load()
  }, 3000)
}

function openCreate() {
  editingId.value = null
  Object.assign(form, {
    name: '',
    url: '',
    enabled: true,
    tags: [],
    group_name: 'default',
    remark: '',
    update_interval: 3600,
    priority: 100,
  })
  dialogVisible.value = true
}

function openEdit(row: Subscription) {
  editingId.value = row.id
  Object.assign(form, row)
  dialogVisible.value = true
}

async function save() {
  if (editingId.value) await http.put(`/subscriptions/${editingId.value}`, form)
  else await http.post('/subscriptions', form)
  dialogVisible.value = false
  ElMessage.success('已保存，节点池将在后台同步')
  await load()
  reloadSoon()
}

async function refresh(id: number) {
  await http.post(`/subscriptions/${id}/refresh`)
  ElMessage.success('刷新完成')
  await load()
}

async function refreshTraffic() {
  trafficRefreshing.value = true
  try {
    const { data } = await http.post('/subscriptions/traffic/refresh')
    items.value = group.value ? data.filter((item: Subscription) => item.group_name === group.value) : data
    const unavailable = items.value.filter((item) => item.traffic_error).length
    if (unavailable) ElMessage.warning(`流量刷新完成，${unavailable} 个订阅异常，已保留上次可用流量`)
    else ElMessage.success('流量刷新完成')
  } finally {
    trafficRefreshing.value = false
  }
}

async function remove(id: number) {
  await ElMessageBox.confirm('确认删除该订阅？', '删除')
  await http.delete(`/subscriptions/${id}`)
  ElMessage.success('已删除，节点池将在后台同步')
  await load()
  reloadSoon()
}

function statusText(value?: string | null) {
  if (value === 'ok') return '正常'
  if (value === 'failed') return '异常'
  if (value === 'syncing') return '同步中'
  if (value === 'disabled') return '已停用'
  return '未同步'
}

function statusTag(value?: string | null) {
  if (value === 'ok') return 'success'
  if (value === 'failed') return 'danger'
  if (value === 'syncing') return 'warning'
  return 'info'
}

function formatBytes(value?: number) {
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

function trafficPercent(row: Subscription) {
  if (!row.traffic_total) return 0
  return Math.min(100, Math.round((row.traffic_used / row.traffic_total) * 100))
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

onMounted(load)
</script>
