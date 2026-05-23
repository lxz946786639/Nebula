<template>
  <section class="traffic-trend-card">
    <header class="traffic-trend-head">
      <div>
        <strong>{{ chartTitle }}</strong>
        <span>上传、下载与总用量趋势</span>
      </div>
      <div class="traffic-trend-meta">
        <span class="traffic-trend-peak">峰值 {{ formatBytes(peakTotal) }}</span>
        <span class="traffic-trend-legend">
          <i class="is-upload" />上传
        </span>
        <span class="traffic-trend-legend">
          <i class="is-download" />下载
        </span>
        <span class="traffic-trend-legend">
          <i class="is-total" />总用量
        </span>
      </div>
    </header>

    <div v-if="!buckets.length" class="traffic-trend-empty">暂无趋势数据</div>
    <div v-else ref="chartRef" class="traffic-trend-chart" :style="{ height: `${height}px` }" role="img" :aria-label="ariaLabel" />
  </section>
</template>

<script setup lang="ts">
import { BarChart, LineChart } from 'echarts/charts'
import type { BarSeriesOption, LineSeriesOption } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from 'echarts/components'
import type {
  DataZoomComponentOption,
  GridComponentOption,
  TooltipComponentOption,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import type { ComposeOption, EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

type TrafficGranularity = 'hour' | 'day'

type TrafficTrendOption = ComposeOption<
  BarSeriesOption | LineSeriesOption | GridComponentOption | TooltipComponentOption | DataZoomComponentOption
>

interface TrafficTrendBucket {
  at?: string
  label: string
  upload: number
  download: number
  total: number
}

const props = withDefaults(
  defineProps<{
    buckets: TrafficTrendBucket[]
    granularity?: TrafficGranularity
    height?: number
    title?: string
  }>(),
  {
    granularity: 'hour',
    height: 256,
    title: '',
  },
)

const chartRef = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null
let resizeObserver: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const chartTitle = computed(() => props.title || (props.granularity === 'day' ? '近 30 天趋势' : '近 24 小时趋势'))
const peakTotal = computed(() => Math.max(...props.buckets.map((bucket) => Number(bucket.total || 0)), 0))
const ariaLabel = computed(() => `${chartTitle.value}，共 ${props.buckets.length} 个采样点，峰值 ${formatBytes(peakTotal.value)}`)

watch(
  () => [props.buckets, props.granularity, props.height],
  () => {
    void nextTick(renderChart)
  },
  { deep: true },
)

onMounted(() => {
  renderChart()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
  themeObserver = new MutationObserver(() => renderChart())
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-theme', 'style'],
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

function renderChart() {
  if (!chartRef.value || !props.buckets.length) return
  if (!chart) {
    chart = echarts.init(chartRef.value, undefined, { renderer: 'canvas' })
  }
  chart.setOption(buildChartOption(), true)
  chart.resize()
}

function buildChartOption(): TrafficTrendOption {
  const colors = readChartColors()
  const labels = props.buckets.map((bucket) => bucket.label)
  const labelInterval = props.granularity === 'day' ? 2 : 1

  return {
    color: [colors.upload, colors.download, colors.total],
    animationDuration: 420,
    animationEasing: 'cubicOut',
    grid: {
      top: 18,
      right: 12,
      bottom: 34,
      left: 8,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      className: 'traffic-echart-tooltip',
      backgroundColor: colors.panel,
      borderColor: colors.line,
      borderWidth: 1,
      textStyle: {
        color: colors.heading,
        fontSize: 12,
      },
      axisPointer: {
        type: 'shadow',
        shadowStyle: {
          color: colors.axisPointer,
        },
      },
      formatter: formatTooltip,
    },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: true,
      axisTick: {
        show: false,
      },
      axisLine: {
        lineStyle: {
          color: colors.line,
        },
      },
      axisLabel: {
        color: colors.muted,
        fontSize: 11,
        interval: labelInterval,
      },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitNumber: 3,
      axisLabel: {
        color: colors.muted,
        fontSize: 11,
        formatter: (value: number) => formatBytes(value),
      },
      splitLine: {
        lineStyle: {
          color: colors.grid,
        },
      },
    },
    dataZoom: [
      {
        type: 'inside',
        zoomOnMouseWheel: false,
        moveOnMouseMove: true,
        moveOnMouseWheel: true,
      },
    ],
    series: [
      {
        name: '上传',
        type: 'bar',
        stack: 'traffic',
        data: props.buckets.map((bucket) => Math.max(0, Number(bucket.upload || 0))),
        barMaxWidth: props.granularity === 'day' ? 16 : 18,
        emphasis: {
          focus: 'series',
        },
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
        },
      },
      {
        name: '下载',
        type: 'bar',
        stack: 'traffic',
        data: props.buckets.map((bucket) => Math.max(0, Number(bucket.download || 0))),
        barMaxWidth: props.granularity === 'day' ? 16 : 18,
        emphasis: {
          focus: 'series',
        },
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
        },
      },
      {
        name: '总用量',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: props.buckets.map((bucket) => Math.max(0, Number(bucket.total || 0))),
        lineStyle: {
          width: 2,
        },
        areaStyle: {
          opacity: 0.08,
        },
        emphasis: {
          focus: 'series',
        },
      },
    ],
  }
}

function formatTooltip(params: unknown) {
  const items = Array.isArray(params) ? params : [params]
  const first = items[0] as { dataIndex?: number } | undefined
  const index = Number(first?.dataIndex ?? 0)
  const bucket = props.buckets[index]
  if (!bucket) return ''

  return `
    <div class="traffic-echart-tip">
      <strong>${escapeHtml(bucketTitle(bucket))}</strong>
      <dl>
        <div><dt>总用量</dt><dd>${formatBytes(bucket.total)}</dd></div>
        <div><dt><i class="is-upload"></i>上传</dt><dd>${formatBytes(bucket.upload)}</dd></div>
        <div><dt><i class="is-download"></i>下载</dt><dd>${formatBytes(bucket.download)}</dd></div>
      </dl>
    </div>
  `
}

function bucketTitle(bucket: TrafficTrendBucket) {
  return `${props.granularity === 'day' ? '日期' : '时间'} ${bucket.label}`
}

function readChartColors() {
  const styles = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback
  return {
    upload: read('--accent-hover', '#d9795f'),
    download: read('--success', '#5f8d69'),
    total: read('--warning', '#a9792f'),
    panel: read('--panel', '#fffdf7'),
    line: read('--line', '#d6d2c7'),
    grid: colorWithAlpha(read('--line', '#d6d2c7'), 0.5),
    muted: read('--muted', '#67675d'),
    heading: read('--heading', '#181914'),
    axisPointer: colorWithAlpha(read('--accent', '#bd6b55'), 0.1),
  }
}

function colorWithAlpha(color: string, alpha: number) {
  if (!color.startsWith('#')) return color
  const hex = color.replace('#', '')
  if (hex.length !== 3 && hex.length !== 6) return color
  const normalized = hex.length === 3 ? hex.split('').map((item) => item + item).join('') : hex
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
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

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    const map: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }
    return map[char] || char
  })
}
</script>

<style scoped>
.traffic-trend-card {
  min-width: 0;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--el-fill-color-lighter) 92%, var(--accent) 8%), var(--el-fill-color-lighter)),
    var(--el-fill-color-lighter);
  padding: 12px;
}

.traffic-trend-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.traffic-trend-head > div:first-child {
  display: grid;
  gap: 3px;
  min-width: 160px;
}

.traffic-trend-head strong {
  color: var(--heading);
  font-size: 14px;
}

.traffic-trend-head span,
.traffic-trend-peak,
.traffic-trend-legend {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.traffic-trend-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px 10px;
}

.traffic-trend-peak {
  border: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
  border-radius: 999px;
  padding: 2px 7px;
  background: color-mix(in srgb, var(--panel) 68%, transparent);
  color: var(--heading);
  font-weight: 650;
}

.traffic-trend-legend {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.traffic-trend-legend i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.traffic-trend-legend .is-upload {
  background: var(--accent-hover);
}

.traffic-trend-legend .is-download {
  background: var(--success);
}

.traffic-trend-legend .is-total {
  width: 14px;
  height: 2px;
  border-radius: 999px;
  background: var(--warning);
}

.traffic-trend-chart {
  width: 100%;
  min-height: 220px;
}

.traffic-trend-empty {
  display: grid;
  min-height: 220px;
  place-items: center;
  color: var(--muted);
  font-size: 13px;
}

:global(.traffic-echart-tooltip) {
  max-width: 260px;
  border-radius: 8px !important;
  box-shadow: var(--shadow) !important;
}

:global(.traffic-echart-tip) {
  display: grid;
  gap: 8px;
  min-width: 170px;
}

:global(.traffic-echart-tip strong) {
  color: var(--heading);
  font-size: 13px;
  font-weight: 750;
}

:global(.traffic-echart-tip dl) {
  display: grid;
  gap: 6px;
  margin: 0;
}

:global(.traffic-echart-tip dl > div) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

:global(.traffic-echart-tip dt),
:global(.traffic-echart-tip dd) {
  margin: 0;
}

:global(.traffic-echart-tip dt) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
}

:global(.traffic-echart-tip dt i) {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

:global(.traffic-echart-tip .is-upload) {
  background: var(--accent-hover);
}

:global(.traffic-echart-tip .is-download) {
  background: var(--success);
}

:global(.traffic-echart-tip dd) {
  color: var(--heading);
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 600px) {
  .traffic-trend-card {
    padding: 10px;
  }

  .traffic-trend-meta {
    justify-content: flex-start;
  }

  .traffic-trend-chart {
    min-height: 210px;
  }
}
</style>
