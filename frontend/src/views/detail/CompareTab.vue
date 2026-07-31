<template>
  <div class="compare-tab">
    <!-- 未解析引导态 -->
    <div v-if="doc.status !== 'parsed'" class="card">
      <EmptyState icon="TrendCharts" title="解析完成后才能对比" desc="对比基于结构化抽取结果，请先完成文档解析并抽取同一 Schema">
        <el-button type="primary" disabled>等待解析完成</el-button>
      </EmptyState>
    </div>

    <template v-else>
      <!-- 加载失败 -->
      <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load" /></div>
      <!-- 加载中 -->
      <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="5" /></div>

      <template v-else>
        <!-- 对比配置行 -->
        <div class="top-bar card">
          <div class="pick">
            <span class="label">文档 A</span>
            <el-tag size="large" effect="plain" class="doc-a">{{ doc.original_name }}</el-tag>
          </div>
          <el-icon class="vs"><Switch /></el-icon>
          <div class="pick">
            <span class="label">文档 B</span>
            <el-select v-model="docBId" placeholder="选择对比文档" style="width: 220px" :disabled="taskRunning">
              <el-option v-for="d in candidateDocs" :key="d.id" :label="d.original_name" :value="d.id" />
            </el-select>
          </div>
          <div class="pick">
            <span class="label">Schema</span>
            <el-select v-model="schemaId" placeholder="选择 Schema" style="width: 170px" :disabled="taskRunning" @change="onSchemaChange">
              <el-option v-for="s in schemaOptions" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </div>
          <div class="spacer"></div>
          <el-button type="primary" :loading="taskRunning" :disabled="!docBId || !schemaId" @click="startCompare">
            <el-icon><Switch /></el-icon>开始对比
          </el-button>
        </div>

        <TaskProgress v-if="taskRunning" :running="taskRunning" :progress="progress" :message="message" label="正在对比文档…" class="task-line" />
        <TaskProgress v-else-if="taskError" :error="taskError" label="对比失败" class="task-line" />

        <!-- 对比历史 -->
        <div v-if="compares.length" class="history card">
          <div class="history-title"><el-icon><Clock /></el-icon>对比历史（本文档参与）</div>
          <div class="history-list">
            <div v-for="c in compares" :key="c.id" class="history-item" :class="{ active: current && current.id === c.id }" @click="viewCompare(c.id)">
              <span class="h-name" :title="c.doc_a_name">{{ c.doc_a_name }}</span>
              <el-icon class="h-vs"><Right /></el-icon>
              <span class="h-name" :title="c.doc_b_name">{{ c.doc_b_name }}</span>
              <el-tag size="small" effect="plain">{{ c.schema_name }}</el-tag>
              <span class="h-time">{{ formatTime(c.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 结果区 -->
        <template v-if="current">
          <!-- 差异摘要 -->
          <div class="card summary-card">
            <div class="summary-head"><el-icon><DataAnalysis /></el-icon>差异摘要<span class="src-tag">{{ current.source === 'llm' ? 'LLM 智能对比' : '规则对比（演示模式）' }}</span></div>
            <MarkdownView :content="current.summary || '暂无摘要'" />
          </div>

          <!-- 字段差异 -->
          <div class="card table-card">
            <div class="sec-title">字段差异</div>
            <CompareTable :rows="current.field_diff" :doc-a-name="current.doc_a_name" :doc-b-name="current.doc_b_name" />
          </div>

          <!-- 章节相似度 -->
          <div class="card sec-card">
            <div class="sec-title">章节相似度</div>
            <div v-if="current.section_diff.length" class="sec-list">
              <div v-for="s in current.section_diff" :key="s.title" class="sec-row">
                <span class="sec-name" :title="s.title">{{ s.title }}</span>
                <StatusBadge :value="s.status" map="section" />
                <div class="sim"><ConfidenceBar :value="s.similarity" /></div>
              </div>
            </div>
            <div v-else class="muted">暂无章节数据</div>
          </div>

          <div class="result-foot">
            <span class="muted">共 {{ current.field_diff.length }} 个字段 · {{ current.section_diff.length }} 个章节</span>
            <div class="foot-ops">
              <el-button size="small" @click="exportReport('md')"><el-icon><Download /></el-icon>导出 Markdown</el-button>
              <el-button size="small" @click="exportReport('html')"><el-icon><Download /></el-icon>导出 HTML</el-button>
            </div>
          </div>
        </template>

        <!-- 空态 -->
        <div v-else class="card">
          <EmptyState v-if="schemaOptions.length === 0" icon="TrendCharts" title="暂无可对比文档" desc="先用同一 Schema 对至少两份文档完成抽取（可在「抽取」页签操作），再回来对比">
            <el-button type="primary" @click="$emit('gotoExtract')"><el-icon><MagicStick /></el-icon>去抽取</el-button>
          </EmptyState>
          <EmptyState v-else icon="Select" title="选择文档开始对比" desc="选择另一份已完成同一 Schema 抽取的文档，点击「开始对比」生成差异报告" />
        </div>
      </template>
    </template>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts, Switch, Clock, Right, DataAnalysis, Download, MagicStick, Select } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import { useTask } from '@/composables/useTask'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ConfidenceBar from '@/components/ConfidenceBar.vue'
import CompareTable from '@/components/CompareTable.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import MarkdownView from '@/components/MarkdownView.vue'
import { formatTime } from '@/utils/format'

const props = defineProps({ doc: { type: Object, required: true } })
defineEmits(['gotoExtract'])

const schemas = ref([])
const docs = ref([])
const docSchemas = ref({})       // docId -> [schemaId]
const myExtractions = ref([])    // 当前文档的抽取记录
const schemaOptions = ref([])    // 双方都有抽取的 Schema
const candidateDocs = ref([])    // 当前 Schema 下可对比的文档
const compares = ref([])
const current = ref(null)
const schemaId = ref(null)
const docBId = ref(null)
const loading = ref(true)
const loadError = ref('')
const { running: taskRunning, progress, message, error: taskError, run } = useTask()

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [schemaList, docRes, extList, cmpList] = await Promise.all([
      api.listSchemas(),
      api.listDocuments({ page: 1, page_size: 100 }),
      api.listExtractions(props.doc.id),
      api.listCompares(props.doc.id),
    ])
    schemas.value = schemaList
    myExtractions.value = extList
    compares.value = cmpList
    docs.value = (docRes.items || []).filter((d) => d.id !== props.doc.id && d.status === 'parsed')

    const maps = await Promise.all(
      docs.value.map((d) =>
        api.listExtractions(d.id).then((list) => ({ id: d.id, schemas: list.map((e) => e.schema_id) })).catch(() => null)
      )
    )
    const map = {}
    for (const m of maps) if (m) map[m.id] = m.schemas
    docSchemas.value = map

    const mine = new Set(extList.map((e) => e.schema_id))
    schemaOptions.value = schemaList.filter((s) => mine.has(s.id) && docs.value.some((d) => (map[d.id] || []).includes(s.id)))
    if (!schemaId.value || !schemaOptions.value.some((s) => s.id === schemaId.value)) {
      schemaId.value = schemaOptions.value.length ? schemaOptions.value[0].id : null
    }
    refreshCandidates()
    if (cmpList.length && !current.value) current.value = cmpList[cmpList.length - 1]
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
function refreshCandidates() {
  if (!schemaId.value) {
    candidateDocs.value = []
    docBId.value = null
    return
  }
  candidateDocs.value = docs.value.filter((d) => (docSchemas.value[d.id] || []).includes(schemaId.value))
  if (!candidateDocs.value.some((d) => d.id === docBId.value)) {
    docBId.value = candidateDocs.value.length ? candidateDocs.value[0].id : null
  }
}
function onSchemaChange() {
  refreshCandidates()
}
async function startCompare() {
  if (!docBId.value || !schemaId.value) return
  taskError.value = ''
  try {
    const body = await api.startCompare({ doc_a_id: props.doc.id, doc_b_id: docBId.value, schema_id: schemaId.value })
    await run(body.task_id)
    compares.value = await api.listCompares(props.doc.id)
    const newest = compares.value.reduce((a, b) => (b.id > a.id ? b : a), compares.value[0])
    current.value = newest
    ElMessage.success('对比完成')
  } catch (e) {
    ElMessage.error(e.message || '对比失败')
  }
}
async function viewCompare(id) {
  try {
    current.value = await api.getCompare(id)
  } catch (e) {
    ElMessage.error(e.message || '加载对比结果失败')
  }
}
function exportReport(fmt) {
  if (!current.value) return
  window.open(api.exportCompare(current.value.id, fmt), '_blank')
}
onMounted(load)
</script>
<style scoped>
.top-bar { display: flex; align-items: center; gap: 14px; padding: 14px 16px; margin-bottom: 14px; flex-wrap: wrap; }
.pick { display: flex; align-items: center; gap: 8px; }
.label { font-size: 13px; font-weight: 600; color: var(--dm-text); white-space: nowrap; }
.doc-a { max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
.vs { color: var(--dm-primary); font-size: 18px; }
.spacer { flex: 1; }
.task-line { margin-bottom: 14px; }
.history { padding: 12px 16px; margin-bottom: 14px; }
.history-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--dm-text); margin-bottom: 8px; }
.history-list { display: flex; flex-wrap: wrap; gap: 8px; }
.history-item { display: flex; align-items: center; gap: 8px; padding: 7px 12px; border: 1px solid var(--dm-border); border-radius: 10px; cursor: pointer; font-size: 12.5px; transition: all .15s; max-width: 420px; }
.history-item:hover { border-color: #c7d8f2; background: #f8fafc; }
.history-item.active { border-color: var(--dm-primary); background: var(--dm-primary-light); }
.h-name { max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--dm-text); }
.h-vs { color: var(--dm-text-muted); font-size: 12px; }
.h-time { font-size: 11px; color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.summary-card { padding: 16px 20px; margin-bottom: 14px; }
.summary-head { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: var(--dm-text); margin-bottom: 10px; }
.src-tag { font-size: 11px; font-weight: 400; background: var(--dm-primary-light); color: var(--dm-primary); padding: 2px 8px; border-radius: 999px; }
.table-card { padding: 14px 12px 12px; margin-bottom: 14px; }
.sec-title { font-size: 14px; font-weight: 700; color: var(--dm-text); padding: 0 8px 10px; }
.sec-card { padding: 14px 16px 16px; margin-bottom: 14px; }
.sec-list { display: flex; flex-direction: column; }
.sec-row { display: flex; align-items: center; gap: 14px; padding: 9px 8px; border-bottom: 1px solid #f1f5f9; }
.sec-row:last-child { border-bottom: none; }
.sec-name { flex: 1; min-width: 0; font-size: 13px; color: var(--dm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sim { width: 150px; }
.result-foot { display: flex; align-items: center; justify-content: space-between; padding: 2px 4px 12px; }
.foot-ops { display: flex; gap: 8px; }
.muted { color: #b6c2d2; font-size: 12px; }
</style>