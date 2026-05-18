<template>
  <section class="surface list-page">
    <div class="toolbar">
      <div class="toolbar-filters">
        <el-input v-model="q" class="toolbar-filter-search" placeholder="搜索" clearable @change="load" />
        <el-input v-model="country" class="toolbar-filter-compact" placeholder="国家/地区" clearable @change="load" />
        <el-input v-model="group" class="toolbar-filter-compact" placeholder="分组" clearable @change="load" />
        <el-select v-model="enabledFilter" class="toolbar-filter-status" placeholder="状态" @change="load">
          <el-option label="全部状态" value="" />
          <el-option label="已启用" value="true" />
          <el-option label="已停用" value="false" />
        </el-select>
      </div>
      <div class="toolbar-actions">
        <el-button :icon="Setting" :loading="settingsLoading" @click="openNodeSettings">节点池配置</el-button>
        <el-button :icon="Refresh" @click="load">重新加载</el-button>
        <el-button :icon="Connection" :loading="testing" @click="testLatency">一键测速</el-button>
        <el-button type="primary" :icon="Refresh" :loading="syncing" @click="refreshPool">同步节点池</el-button>
      </div>
    </div>
    <el-table class="list-table desktop-table" :data="nodes" stripe height="100%" empty-text="暂无节点，点击同步节点池">
      <el-table-column label="启用" width="86">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" @change="() => updateEnabled(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="节点" min-width="240" show-overflow-tooltip />
      <el-table-column prop="type" label="协议" width="100" />
      <el-table-column prop="server" label="服务器" min-width="180" show-overflow-tooltip />
      <el-table-column prop="port" label="端口" width="100" />
      <el-table-column prop="country_code" label="国家" width="90" />
      <el-table-column label="延迟" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.latency !== null && row.latency !== undefined" :type="latencyTag(row.latency)" effect="plain">
            {{ row.latency }} ms
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <div class="inline-cell centered">
            <span>{{ row.source_subscription_name || '-' }}</span>
            <el-tooltip v-if="row.source_subscription_status === 'failed'" :content="row.source_subscription_error || '订阅同步异常'" placement="top">
              <el-tag size="small" type="danger" effect="plain">异常</el-tag>
            </el-tooltip>
            <el-tag v-else-if="row.source_subscription_status === 'syncing'" size="small" type="warning" effect="plain">同步中</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="source_group" label="分组" width="100" />
      <el-table-column label="标签" min-width="180" class-name="table-cell-center">
        <template #default="{ row }">
          <div class="tag-cell">
            <el-tag v-for="tag in row.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.last_seen_at) }}</template>
      </el-table-column>
      <el-table-column label="YAML" width="90">
        <template #default="{ row }">
          <el-button :icon="DocumentCopy" circle title="查看节点 YAML" @click="showRaw(row)" />
        </template>
      </el-table-column>
    </el-table>
    <div class="mobile-card-list">
      <el-empty v-if="!nodes.length" description="暂无节点，点击同步节点池" :image-size="72" />
      <article v-for="row in nodes" v-else :key="row.id" class="mobile-card">
        <div class="mobile-card-head">
          <div class="mobile-card-title">
            <strong>{{ row.name }}</strong>
            <span>{{ row.server || '-' }}{{ row.port ? `:${row.port}` : '' }}</span>
          </div>
          <el-switch v-model="row.enabled" @change="() => updateEnabled(row)" />
        </div>
        <div class="mobile-card-meta">
          <el-tag size="small" effect="plain">{{ row.type || '-' }}</el-tag>
          <el-tag v-if="row.country_code" size="small" effect="plain">{{ row.country_code }}</el-tag>
          <el-tag v-if="row.latency !== null && row.latency !== undefined" size="small" :type="latencyTag(row.latency)" effect="plain">
            {{ row.latency }} ms
          </el-tag>
        </div>
        <dl class="mobile-kv">
          <div>
            <dt>来源</dt>
            <dd>
              {{ row.source_subscription_name || '-' }}
              <el-tag v-if="row.source_subscription_status === 'failed'" size="small" type="danger" effect="plain">异常</el-tag>
              <el-tag v-else-if="row.source_subscription_status === 'syncing'" size="small" type="warning" effect="plain">同步中</el-tag>
            </dd>
          </div>
          <div>
            <dt>分组</dt>
            <dd>{{ row.source_group || '-' }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ formatDateTime(row.last_seen_at) }}</dd>
          </div>
        </dl>
        <div v-if="row.tags?.length" class="mobile-tags">
          <el-tag v-for="tag in row.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
        </div>
        <div class="mobile-card-actions">
          <el-button :icon="DocumentCopy" @click="showRaw(row)">查看 YAML</el-button>
        </div>
      </article>
    </div>
  </section>
  <el-dialog v-model="rawVisible" title="节点 YAML" width="680px">
    <textarea class="code-editor" readonly :value="rawText" />
  </el-dialog>

  <el-dialog v-model="settingsDialogVisible" title="节点池配置" width="620px">
    <el-form v-loading="settingsLoading" label-position="top">
      <el-form-item v-for="item in nodeSettings" :key="item.key" :label="settingLabel(item.key)">
        <el-input v-model="nodeValues[item.key]" :placeholder="settingPlaceholder(item.key)" />
        <small>{{ settingDescription(item) }}</small>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="settingsDialogVisible = false">取消</el-button>
      <el-button :icon="Refresh" :loading="settingsLoading" @click="loadNodeSettings">刷新</el-button>
      <el-button type="primary" :icon="Check" :loading="settingsSaving" @click="saveNodeSettings">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Check, Connection, DocumentCopy, Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import http from '@/api/http'
import { formatDateTime } from '@/utils/datetime'

interface NodeItem {
  id: number
  name: string
  type?: string
  server?: string
  port?: number | string
  country_code?: string
  latency?: number | null
  tags: string[]
  source_subscription_name?: string
  source_subscription_status?: string | null
  source_subscription_error?: string | null
  source_group?: string
  enabled: boolean
  last_seen_at?: string | null
  raw: Record<string, unknown>
}

interface SettingItem {
  key: string
  value: string | null
  secret: boolean
  description?: string
}

const nodeSettingMeta: Record<string, { label: string; description: string; placeholder?: string }> = {
  node_filter_patterns: {
    label: '节点过滤通配符',
    description: '同步节点池时按节点名称过滤，多个规则用英文逗号分隔；保存后会自动触发一次节点池同步。',
    placeholder: '*天*,*剩余*',
  },
}

const nodes = ref<NodeItem[]>([])
const nodeSettings = ref<SettingItem[]>([])
const nodeValues = reactive<Record<string, string | null>>({})
const q = ref('')
const country = ref('')
const group = ref('')
const enabledFilter = ref('')
const syncing = ref(false)
const testing = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settingsDialogVisible = ref(false)
const rawVisible = ref(false)
const rawText = ref('')

async function load() {
  const { data } = await http.get('/nodes', {
    params: {
      q: q.value || undefined,
      country: country.value || undefined,
      group: group.value || undefined,
      enabled: enabledFilter.value === '' ? undefined : enabledFilter.value === 'true',
    },
  })
  nodes.value = data.items
}

async function loadNodeSettings() {
  settingsLoading.value = true
  try {
    const { data } = await http.get<SettingItem[]>('/settings', { params: { scope: 'node_pool' } })
    nodeSettings.value = data
    for (const item of data) nodeValues[item.key] = item.value
  } finally {
    settingsLoading.value = false
  }
}

async function openNodeSettings() {
  settingsDialogVisible.value = true
  if (!nodeSettings.value.length) await loadNodeSettings()
}

async function saveNodeSettings() {
  settingsSaving.value = true
  try {
    const settings: Record<string, string | null> = {}
    for (const item of nodeSettings.value) settings[item.key] = nodeValues[item.key]
    await http.put('/settings', { settings })
    ElMessage.success('节点池配置已保存，下次同步生效')
    await loadNodeSettings()
  } finally {
    settingsSaving.value = false
  }
}

function settingLabel(key: string) {
  return nodeSettingMeta[key]?.label || key
}

function settingDescription(item: SettingItem) {
  return nodeSettingMeta[item.key]?.description || item.description || ''
}

function settingPlaceholder(key: string) {
  return nodeSettingMeta[key]?.placeholder || ''
}

async function refreshPool() {
  syncing.value = true
  try {
    const { data } = await http.post('/nodes/refresh', null, {
      params: { group: group.value || undefined },
    })
    if (data.errors?.length) {
      ElMessage.warning(`同步完成，${data.failed_subscriptions} 个订阅失败`)
    } else {
      const filteredText = data.filtered_nodes ? `，过滤 ${data.filtered_nodes} 个节点` : ''
      ElMessage.success(`同步完成，清空 ${data.cleared_nodes} 个旧节点，写入 ${data.synced_nodes} 个节点${filteredText}`)
    }
    await load()
  } finally {
    syncing.value = false
  }
}

async function testLatency() {
  testing.value = true
  try {
    const { data } = await http.post('/nodes/test-latency', null, {
      params: {
        group: group.value || undefined,
        enabled: enabledFilter.value === '' ? true : enabledFilter.value === 'true',
      },
    })
    ElMessage.success(`测速完成，在线 ${data.online_nodes} 个，失败 ${data.failed_nodes} 个`)
    await load()
  } finally {
    testing.value = false
  }
}

async function updateEnabled(row: NodeItem) {
  const enabled = row.enabled
  try {
    await http.put(`/nodes/${row.id}`, { enabled })
    ElMessage.success(enabled ? '节点已启用' : '节点已停用')
  } catch {
    row.enabled = !enabled
    ElMessage.error('更新节点状态失败')
  }
}

function latencyTag(value: number) {
  if (value <= 300) return 'success'
  if (value <= 800) return 'warning'
  return 'danger'
}

function showRaw(row: NodeItem) {
  rawText.value = JSON.stringify(row.raw, null, 2)
  rawVisible.value = true
}

onMounted(load)
</script>
