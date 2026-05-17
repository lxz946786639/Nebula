<template>
  <section class="surface list-page">
    <div class="toolbar">
      <span></span>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增规则</el-button>
    </div>
    <el-table class="list-table" :data="items" stripe height="100%">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="remote_config_url" label="远程配置" min-width="260" show-overflow-tooltip />
      <el-table-column label="默认" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success">默认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button :icon="Edit" circle title="编辑规则" @click="openEdit(row)" />
          <el-button :icon="Delete" circle title="删除规则" type="danger" @click="remove(row.id)" />
        </template>
      </el-table-column>
    </el-table>
  </section>

  <el-dialog v-model="visible" :title="editingId ? '编辑规则' : '新增规则'" width="760px">
    <el-form label-position="top">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" /></el-form-item>
      <el-form-item label="远程配置 URL"><el-input v-model="form.remote_config_url" /></el-form-item>
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

interface RuleItem {
  id: number
  name: string
  description?: string
  remote_config_url?: string
  yaml_content?: string
  is_default: boolean
}

const items = ref<RuleItem[]>([])
const visible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  description: '',
  remote_config_url: '',
  yaml_content: '',
  is_default: false,
})

async function load() {
  const { data } = await http.get('/rules')
  items.value = data
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', remote_config_url: '', yaml_content: '', is_default: false })
  visible.value = true
}

function openEdit(row: RuleItem) {
  editingId.value = row.id
  Object.assign(form, row)
  visible.value = true
}

async function save() {
  if (editingId.value) await http.put(`/rules/${editingId.value}`, form)
  else await http.post('/rules', form)
  visible.value = false
  await load()
}

async function remove(id: number) {
  await ElMessageBox.confirm('确认删除该规则？', '删除')
  await http.delete(`/rules/${id}`)
  await load()
}

onMounted(load)
</script>
