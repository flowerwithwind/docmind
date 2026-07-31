<template>
  <div class="result-chart">
    <!-- 空数据态 -->
    <EmptyState v-if="!rows.length" icon="Grid" title="暂无图表数据" desc="当前查询结果没有可绘制的数据行" />
    <!-- line / bar：ECharts 渲染 -->
    <div v-else-if="isEChart" ref="chartEl" class="chart-canvas" :style="{ height }"></div>
    <!-- table 类型：直接渲染数据表 -->
    <el-table v-else :data="tableData" size="small" border class="chart-table">
      <el-table-column v-for="col in columns" :key="col" :label="col" min-width="120" show-overflow-tooltip>
        <template #default="{ row }"><span class="cell">{{ text(row[col]) }}</span></template>
      </el-table-column>
    </el-table>
  </div>
</template>
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import EmptyState from '@/components/EmptyState.vue'
import { buildChartOption } from '@/utils/chart'

const props = defineProps({
  chart: { type: Object, default: () => ({ type: 'table', columns: [], rows: [] }) },
  height: { type: String, default: '340px' },
})
const chartEl = ref(null)
let instance = null
const columns = computed(() => (props.chart && props.chart.columns) || [])
const rows = computed(() => (props.chart && props.chart.rows) || [])
const isEChart = computed(() => props.chart && (props.chart.type === 'line' || props.chart.type === 'bar'))
const tableData = computed(() =>
  rows.value.map((r) => Object.fromEntries(columns.value.map((c, i) => [c, r[i]]))),
)
function text(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
function renderChart() {
  if (!isEChart.value || !chartEl.value) return
  if (!instance) instance = echarts.init(chartEl.value)
  instance.setOption(buildChartOption(props.chart), true)
}
async function refresh() {
  if (!isEChart.value) return
  await nextTick()
  renderChart()
  if (instance) instance.resize()
}
watch(() => props.chart, refresh, { deep: true })
onMounted(refresh)
onBeforeUnmount(() => {
  if (instance) {
    instance.dispose()
    instance = null
  }
})
</script>
<style scoped>
.result-chart { width: 100%; }
.chart-canvas { width: 100%; }
.chart-table { width: 100%; }
.cell { font-size: 12.5px; font-variant-numeric: tabular-nums; }
</style>
