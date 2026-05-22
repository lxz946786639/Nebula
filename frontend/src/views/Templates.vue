<template>
  <section class="surface list-page">
    <div class="toolbar">
      <span></span>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增模板</el-button>
    </div>
    <div class="table-wrap has-cards desktop-table">
      <el-table class="list-table" :data="items" stripe height="100%">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="target" label="目标" width="130" />
      <el-table-column prop="config_url" label="配置 URL" min-width="260" show-overflow-tooltip />
      <el-table-column label="默认" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success">默认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button :icon="Edit" circle title="编辑模板" @click="openEdit(row)" />
          <el-button :icon="Delete" circle title="删除模板" type="danger" @click="remove(row.id)" />
        </template>
      </el-table-column>
      </el-table>
    </div>
    <div class="mobile-card-list data-cards">
      <el-empty v-if="!items.length" description="暂无模板" :image-size="72" />
      <article v-for="row in items" v-else :key="row.id" class="mobile-card">
        <div class="mobile-card-head">
          <div class="mobile-card-title">
            <strong>{{ row.name }}</strong>
            <span>{{ targetLabel(row.target) }}</span>
          </div>
          <el-tag v-if="row.is_default" type="success" effect="plain">默认</el-tag>
        </div>
        <dl class="mobile-kv">
          <div>
            <dt>配置 URL</dt>
            <dd>{{ row.config_url || '-' }}</dd>
          </div>
          <div>
            <dt>YAML</dt>
            <dd>{{ row.yaml_content ? '已填写本地内容' : '未填写' }}</dd>
          </div>
        </dl>
        <div class="mobile-card-actions">
          <el-button :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button :icon="Delete" type="danger" @click="remove(row.id)">删除</el-button>
        </div>
      </article>
    </div>
  </section>

  <el-dialog v-model="visible" :title="editingId ? '编辑模板' : '新增模板'" width="760px">
    <el-form label-position="top">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="目标">
        <el-select v-model="form.target" style="width: 100%">
          <el-option label="Clash" value="clash" />
          <el-option label="Mihomo" value="clashmeta" />
          <el-option label="sing-box" value="singbox" />
          <el-option label="v2ray" value="v2ray" />
        </el-select>
      </el-form-item>
      <el-form-item label="配置 URL"><el-input v-model="form.config_url" /></el-form-item>
      <el-form-item label="YAML">
        <textarea v-model="form.yaml_content" class="code-editor" />
      </el-form-item>
      <el-form-item label="默认"><el-switch v-model="form.is_default" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Delete, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import http from '@/api/http'

interface TemplateItem {
  id: number
  name: string
  target: string
  config_url?: string
  yaml_content?: string
  is_default: boolean
}

const items = ref<TemplateItem[]>([])
const visible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  target: 'clashmeta',
  config_url: '',
  yaml_content: '',
  is_default: false,
})

async function load() {
  const { data } = await http.get('/templates')
  items.value = data
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', target: 'clashmeta', config_url: '', yaml_content: '', is_default: false })
  visible.value = true
}

function openEdit(row: TemplateItem) {
  editingId.value = row.id
  Object.assign(form, row)
  visible.value = true
}

async function save() {
  if (editingId.value) await http.put(`/templates/${editingId.value}`, form)
  else await http.post('/templates', form)
  visible.value = false
  await load()
}

async function remove(id: number) {
  await ElMessageBox.confirm('确认删除该模板？', '删除')
  await http.delete(`/templates/${id}`)
  await load()
}

function targetLabel(value: string) {
  const labels: Record<string, string> = {
    clash: 'Clash',
    clashmeta: 'Mihomo',
    singbox: 'sing-box',
    v2ray: 'v2ray',
  }
  return labels[value] || value
}

onMounted(load)
</script>
