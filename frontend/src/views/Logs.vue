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
          :format="DATE_TIME_PICKER_FORMAT"
          :value-format="DATE_TIME_PICKER_FORMAT"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          range-separator="至"
          style="width: 380px"
          @change="resetAndLoad"
        />
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="logs-table-wrap desktop-table">
      <el-table v-loading="loading" class="list-table" :data="items" stripe height="100%" empty-text="暂无日志">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-tag effect="plain">{{ row.type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action_label" label="动作" width="110" />
        <el-table-column prop="actor" label="操作人" width="120" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="190" show-overflow-tooltip />
        <el-table-column prop="description" label="详情" min-width="360" show-overflow-tooltip class-name="table-cell-left" />
      </el-table>
    </div>
    <div class="mobile-card-list">
      <el-empty v-if="!items.length && !loading" description="暂无日志" :image-size="72" />
      <article v-for="row in items" v-else :key="row.id" class="mobile-card">
        <div class="mobile-card-head">
          <div class="mobile-card-title">
            <strong>{{ row.title }}</strong>
            <span>{{ formatDateTime(row.created_at) }}</span>
          </div>
          <el-tag effect="plain">{{ row.type_label }}</el-tag>
        </div>
        <div class="mobile-card-meta">
          <el-tag size="small" effect="plain">{{ row.action_label }}</el-tag>
          <span>{{ row.actor || '-' }}</span>
        </div>
        <dl class="mobile-kv">
          <div>
            <dt>详情</dt>
            <dd>{{ row.description || '-' }}</dd>
          </div>
        </dl>
      </article>
    </div>

    <div class="table-pagination desktop-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="pageSizes"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @size-change="resetAndLoad"
        @current-change="load"
      />
    </div>
    <div class="mobile-pagination">
      <div class="mobile-pagination-meta">
        <span>共 {{ total }} 条</span>
        <el-select v-model="pageSize" class="mobile-page-size" @change="resetAndLoad">
          <el-option v-for="size in pageSizes" :key="size" :label="`${size}/页`" :value="size" />
        </el-select>
      </div>
      <div class="mobile-pagination-controls">
        <el-button :icon="ArrowLeft" :disabled="loading || page <= 1" aria-label="上一页" @click="goPage(page - 1)" />
        <span class="mobile-page-indicator">{{ page }} / {{ pageCount }}</span>
        <el-button :icon="ArrowRight" :disabled="loading || page >= pageCount" aria-label="下一页" @click="goPage(page + 1)" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ArrowLeft, ArrowRight, Refresh } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'

import http from '@/api/http'
import { DATE_TIME_PICKER_FORMAT, formatDateTime } from '@/utils/datetime'

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
const pageSizes = [20, 50, 100, 200]
const loading = ref(false)
const filters = reactive({
  type: '',
  range: [] as string[],
})
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

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

async function goPage(nextPage: number) {
  const target = Math.min(pageCount.value, Math.max(1, nextPage))
  if (target === page.value) return
  page.value = target
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

.mobile-pagination {
  display: none;
}

@media (max-width: 760px) {
  .logs-table-wrap.desktop-table {
    display: none;
  }

  .log-filters,
  .log-filters :deep(.el-date-editor) {
    width: 100% !important;
  }

  .desktop-pagination {
    display: none;
  }

  .mobile-pagination {
    display: grid;
    flex: 0 0 auto;
    gap: 10px;
    width: 100%;
    min-width: 0;
    padding-top: 14px;
  }

  .mobile-pagination-meta {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 112px;
    gap: 10px;
    align-items: center;
    min-width: 0;
    color: var(--muted);
    font-size: 13px;
  }

  .mobile-page-size {
    width: 112px;
  }

  .mobile-pagination-controls {
    display: grid;
    grid-template-columns: 42px minmax(0, 1fr) 42px;
    gap: 10px;
    align-items: center;
    min-width: 0;
  }

  .mobile-pagination-controls :deep(.el-button) {
    width: 42px;
    min-width: 42px;
    height: 38px;
    min-height: 38px;
    padding: 0;
  }

  .mobile-page-indicator {
    display: inline-flex;
    min-width: 0;
    height: 38px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--panel-soft);
    color: var(--heading);
    font-weight: 700;
  }
}
</style>
