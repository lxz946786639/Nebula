<template>
  <section class="surface form-page">
    <div class="toolbar">
      <el-button :icon="Refresh" @click="load">刷新</el-button>
      <el-button type="primary" :icon="Check" @click="save">保存</el-button>
    </div>
    <el-form class="settings-form" label-position="top">
      <el-form-item v-for="item in items" :key="item.key" :label="settingLabel(item.key)">
        <el-input-number
          v-if="isNumberSetting(item.key)"
          v-model="numberValues[item.key]"
          :min="numberMin(item.key)"
          :max="numberMax(item.key)"
          :step="1"
          :disabled="item.read_only"
          controls-position="right"
          style="width: 100%"
        />
        <el-input
          v-else
          v-model="values[item.key]"
          :type="item.secret ? 'password' : 'text'"
          :placeholder="settingPlaceholder(item.key)"
          :show-password="item.secret"
          :disabled="item.read_only"
        />
        <small v-if="settingDescription(item)">{{ settingDescription(item) }}</small>
      </el-form-item>
    </el-form>
  </section>
</template>

<script setup lang="ts">
import { Check, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import http from '@/api/http'

interface SettingItem {
  key: string
  value: string | null
  secret: boolean
  description?: string
  read_only?: boolean
}

const settingMeta: Record<string, { label: string; description: string; placeholder?: string; type?: 'number'; min?: number; max?: number }> = {
  subscription_public_base_url: {
    label: '订阅公开访问地址',
    description: '用于生成客户端订阅地址；留空时使用当前访问地址。建议填写完整 http(s)://域名[:端口]。',
    placeholder: 'https://nebula.example.com',
  },
  proxy_public_base_url: {
    label: '代理公开访问地址',
    description: '用于生成智能代理地址；留空时使用代理监听地址。只填写域名时端口使用各代理端口，填写端口时使用该公开端口。',
    placeholder: 'nebula.example.com',
  },
  subconverter_url: {
    label: 'subconverter 服务地址',
    description: 'subconverter HTTP API 基础地址。',
    placeholder: 'http://subconverter:25500',
  },
  mihomo_api_url: {
    label: 'Mihomo API 地址',
    description: 'Nebula 访问 Mihomo External Controller 的地址，Docker 部署默认使用容器内网地址。',
    placeholder: 'http://mihomo:9090',
  },
  mihomo_api_secret: {
    label: 'Mihomo API 密钥',
    description: 'Mihomo External Controller 的访问密钥；未配置密钥时可留空。',
    placeholder: '留空表示不使用密钥',
  },
  acl4ssr_config_url: {
    label: 'ACL4SSR 远程规则地址',
    description: '默认 ACL4SSR 远程规则配置地址，用于生成转换配置。',
    placeholder: 'https://raw.githubusercontent.com/...',
  },
  history_retention_smart_proxy_traffic_days: {
    label: '智能代理流量保留天数',
    description: '自动清理智能代理流量采样数据；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_ant_proxy_traffic_days: {
    label: '蚂蚁流量保留天数',
    description: '自动清理蚂蚁代理流量采样数据；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_audit_log_days: {
    label: '日志中心保留天数',
    description: '自动清理日志中心审计日志；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_subscription_traffic_days: {
    label: '订阅流量快照保留天数',
    description: '自动清理订阅流量轮询快照；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_smart_proxy_stability_days: {
    label: '智能代理稳定性保留天数',
    description: '自动清理智能代理稳定性评分样本；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_smart_proxy_health_log_days: {
    label: '健康检测日志保留天数',
    description: '自动清理智能代理健康检测日志；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_smart_proxy_switch_log_days: {
    label: '节点切换历史保留天数',
    description: '自动清理智能代理节点切换历史；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
  history_retention_node_snapshot_days: {
    label: '节点转换快照保留天数',
    description: '自动清理订阅转换生成的节点快照；0 表示关闭该类自动清理。',
    type: 'number',
    min: 0,
    max: 3650,
  },
}

const items = ref<SettingItem[]>([])
const values = reactive<Record<string, string | null>>({})
const numberValues = reactive<Record<string, number | null>>({})

function settingLabel(key: string) {
  return settingMeta[key]?.label || key
}

function settingDescription(item: SettingItem) {
  const base = settingMeta[item.key]?.description || item.description || ''
  const readOnlyNote = item.read_only ? '本地开发环境下此配置由环境变量控制，页面只读。' : ''
  return [base, readOnlyNote].filter(Boolean).join(' ')
}

function settingPlaceholder(key: string) {
  return settingMeta[key]?.placeholder || ''
}

function isNumberSetting(key: string) {
  return settingMeta[key]?.type === 'number'
}

function numberMin(key: string) {
  return settingMeta[key]?.min ?? 0
}

function numberMax(key: string) {
  return settingMeta[key]?.max
}

async function load() {
  const { data } = await http.get('/settings', { params: { scope: 'system' } })
  items.value = data
  for (const item of data) {
    if (isNumberSetting(item.key)) {
      const parsed = Number(item.value)
      numberValues[item.key] = Number.isFinite(parsed) ? parsed : null
    } else {
      values[item.key] = item.value
    }
  }
}

async function save() {
  const payload: Record<string, string | null> = {}
  for (const item of items.value) {
    if (item.read_only) continue
    payload[item.key] = isNumberSetting(item.key) ? String(numberValues[item.key] ?? '') : values[item.key]
  }
  await http.put('/settings', { settings: payload })
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>
