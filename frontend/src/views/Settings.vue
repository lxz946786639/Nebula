<template>
  <section class="surface form-page">
    <div class="toolbar">
      <el-button :icon="Refresh" @click="load">刷新</el-button>
      <el-button type="primary" :icon="Check" @click="save">保存</el-button>
    </div>
    <el-form class="settings-form" label-position="top">
      <el-form-item v-for="item in items" :key="item.key" :label="settingLabel(item.key)">
        <el-input
          v-model="values[item.key]"
          :type="item.secret ? 'password' : 'text'"
          :placeholder="settingPlaceholder(item.key)"
          :show-password="item.secret"
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
}

const settingMeta: Record<string, { label: string; description: string; placeholder?: string }> = {
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
}

const items = ref<SettingItem[]>([])
const values = reactive<Record<string, string | null>>({})

function settingLabel(key: string) {
  return settingMeta[key]?.label || key
}

function settingDescription(item: SettingItem) {
  return settingMeta[item.key]?.description || item.description || ''
}

function settingPlaceholder(key: string) {
  return settingMeta[key]?.placeholder || ''
}

async function load() {
  const { data } = await http.get('/settings', { params: { scope: 'system' } })
  items.value = data
  for (const item of data) values[item.key] = item.value
}

async function save() {
  await http.put('/settings', { settings: values })
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>
