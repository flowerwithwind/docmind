<template>
  <div class="page">
    <div class="head-row">
      <div><h1 class="page-title">修正样本</h1><p class="page-sub">人工确认产生的「模型值 → 人工值」修正样本库，可导出为 JSONL 评测集</p></div>
      <div class="head-ops">
        <el-button :disabled="!total" @click="exportJsonl"><el-icon><Download /></el-icon>导出 JSONL</el-button>
        <el-button type="danger" plain :disabled="!total" @click="clearAll"><el-icon><Delete /></el-icon>清空样本</el-button>
      </div>
    </div>

    <!-- 工具条 -->
    <div class="toolbar card">
      <el-input v-model="query" placeholder="搜索字段 / 模型值 / 人工值…" clearable class="search" @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="schemaId" placeholder="全部 Schema" clearable class="filter" @change="load(1)">
        <el-option v-for="s in schemas" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <div class="spacer"></div>
      <span class="count">共 {{ total }} 条修正样本</span>
    </div>

    <!-- 状态区 -->
    <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load(page)" /></div>
    <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="8" /></div>

    <div v-else-if="items.length" class="card table-card">
      <el-table :data="items">
        <el-table-column label="文档" min-width="180">
          <template #default="{ row }"><span class="doc-name" :title="row.doc_name">{{ row.doc_name }}</span></template>
        </el-table-column>
        <el-table-column label="Schema" width="140">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ row.schema_name }}</el-tag></template>
        </el-table-column>
        <el-table-column label="字段" width="160">
          <template #default="{ row }">
            <div class="f-label">{{ fieldLabel(row.schema_id, row.field_key) }}</div>
            <div class="f-key">{{ row.field_key }}</div>
          </template>
        </el-table-column>
        <el-table-column label="模型值" min-width="150">
          <template #default="{ row }"><span class="model-val">{{ row.model_value || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="人工值" min-width="150">
          <template #default="{ row }"><span class="human-val">{{ row.human_value || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="原文引用" min-width="180">
          <template #default="{ row }"><span class="cite" :title="row.citation">{{ row.citation || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="时间" width="150">
          <template #default="{ row }"><span class="mono">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeSample(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />
      </div>
    </div>

    <div v-else class="card"><EmptyState icon="DataAnalysis" title="暂无修正样本" desc="在文档详情「抽取」页签确认抽取结果时，人工修改过的字段会自动生成修正样本">
      <el-button type="primary" @click="$router.push('/documents')">去文档库体验</el-button>
    </EmptyState></div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Download, Delete, DataAnalysis } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import { formatTime } from '@/utils/format'

const items = ref([])
const schemas = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const query = ref('')
const schemaId = ref(null)
const loading = ref(false)
const loadError = ref('')
const labelMap = ref({}) // schemaId -> {fieldKey: label}

function fieldLabel(schemaId, key) {
  const m = labelMap.value[schemaId]
  return m && m[key] ? m[key] : key
}
async function loadSchemas() {
  try {
    const list = await api.listSchemas()
    schemas.value = list
    const map = {}
    for (const s of list) {
      map[s.id] = {}
      for (const f of s.fields) map[s.id][f.key] = f.label
    }
    labelMap.value = map
  } catch { /* 过滤条件不可用时降级 */ }
}
async function load(p = 1) {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.listSamples({ query: query.value, schema_id: schemaId.value, page: p, page_size: pageSize })
    items.value = res.items
    total.value = res.total
    page.value = p
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
function exportJsonl() {
  window.open(api.exportSamples({ query: query.value, schema_id: schemaId.value }), '_blank')
}
async function removeSample(row) {
  try {
    await ElMessageBox.confirm('删除该条修正样本？', '删除样本', { type: 'warning', confirmButtonText: '删除' })
  } catch { return }
  try {
    await api.deleteSample(row.id)
    ElMessage.success('已删除')
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    load(page.value)
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
async function clearAll() {
  try {
    await ElMessageBox.confirm('将清空全部 ' + total.value + ' 条修正样本，此操作不可恢复。确定继续？', '清空样本', { type: 'error', confirmButtonText: '全部清空' })
  } catch { return }
  try {
    await api.clearSamples()
    ElMessage.success('已清空')
    load(1)
  } catch (e) {
    ElMessage.error(e.message || '清空失败')
  }
}
onMounted(() => { loadSchemas(); load(1) })
</script>
<style scoped>
.head-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.head-ops { display: flex; gap: 10px; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px; }
.search { width: 300px; }
.filter { width: 160px; }
.spacer { flex: 1; }
.count { font-size: 12.5px; color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.table-card { padding: 8px 12px 12px; }
.doc-name { font-size: 13px; font-weight: 600; color: var(--dm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.f-label { font-size: 13px; color: var(--dm-text); font-weight: 600; }
.f-key { font-size: 11px; color: var(--dm-text-faint); font-variant-numeric: tabular-nums; }
.model-val { color: var(--dm-warning); font-size: 12.5px; word-break: break-all; }
.human-val { color: var(--dm-success); font-size: 12.5px; font-weight: 600; word-break: break-all; }
.cite { display: block; font-size: 12px; color: var(--dm-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-variant-numeric: tabular-nums; font-size: 12px; color: var(--dm-text-muted); }
.pager { display: flex; justify-content: flex-end; padding: 14px 4px 2px; }
@media (max-width: 1280px) {
  .toolbar { flex-wrap: wrap; }
  .search { width: 100%; }
}
</style>