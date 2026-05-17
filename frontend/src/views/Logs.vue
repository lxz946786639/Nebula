<template>
  <section class="surface list-page">
    <div class="toolbar">
      <div class="log-filters">
        <el-select v-model="filters.type" placeholder="日志类型" clearable style="width: 170px" @change="resetAndLoad">
          <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-date-picker
          v-model="filters.range"
          type="datetimerange"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          range-separator="至"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 380px"
          @change="resetAndLoad"
        />
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="logs-table-wrap">
      <el-table v-loading="loading" class="list-table" :data="items" stripe height="100%" empty-text="暂无日志">
        <el-table-column prop="created_at_text" label="时间" width="170" />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-tag effect="plain">{{ row.type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action_label" label="动作" width="110" />
        <el-table-column prop="actor" label="操作人" width="120" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="190" show-overflow-tooltip />
        <el-table-column prop="description" label="详情" min-width="360" show-overflow-tooltip />
      </el-table>
    </div>

    <div class="table-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @size-change="resetAndLoad"
        @current-change="load"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'

import http from '@/api/http'

interface LogTypeOption {
  value: string
  label: string
}

interface AuditLogItem {
  id: number
  actor: string
  action: string
  action_label: string
  resource: string
  type: string
  type_label: string
  detail?: string | null
  title: string
  description: string
  created_at: string
  created_at_text: string
}

interface AuditLogPage {
  total: number
  page: number
  page_size: number
  items: AuditLogItem[]
}

const typeOptions = ref<LogTypeOption[]>([])
const items = ref<AuditLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({
  type: '',
  range: [] as string[],
})

async function loadTypes() {
  const { data } = await http.get<LogTypeOption[]>('/logs/types')
  typeOptions.value = data
}

async function load() {
  loading.value = true
  try {
    const [startAt, endAt] = filters.range || []
    const { data } = await http.get<AuditLogPage>('/logs', {
      params: {
        type: filters.type || undefined,
        start_at: startAt || undefined,
        end_at: endAt || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function resetAndLoad() {
  page.value = 1
  await load()
}

onMounted(async () => {
  await loadTypes()
  await load()
})
</script>

<style scoped>
.log-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.logs-table-wrap {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.logs-table-wrap :deep(.el-table) {
  flex: 1 1 auto;
}

.table-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  padding-top: 14px;
}

@media (max-width: 760px) {
  .log-filters,
  .log-filters :deep(.el-date-editor) {
    width: 100% !important;
  }

  .table-pagination {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
