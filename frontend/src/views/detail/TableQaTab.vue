<template>
  <div class="table-qa-tab">
    <!-- 查询输入区 -->
    <div class="qa-bar card">
      <div class="bar-row">
        <div class="pick">
          <span class="label">查询表格</span>
          <el-select v-model="selected" placeholder="请选择表格" filterable :loading="tablesLoading" class="table-pick">
            <el-option-group v-if="docTables.length" label="本文档表格块">
              <el-option v-for="t in docTables" :key="t.key" :value="t.key" :label="t.label" />
            </el-option-group>
            <el-option-group v-if="tables.length" label="已注册可查询表">
              <el-option v-for="t in tables" :key="t.key" :value="t.key" :label="t.label" />
            </el-option-group>
          </el-select>
          <el-tag v-if="selectedMeta" size="small" effect="plain" :type="selectedMeta.source === 'demo' ? 'warning' : 'info'" class="pick-tag">
            {{ selectedMeta.source === 'demo' ? '演示数据' : (selectedMeta.source === 'doc' ? '文档表格' : selectedMeta.rows + ' 行') }}
          </el-tag>
        </div>
        <div class="spacer"></div>
        <el-button type="primary" :loading="loading" :disabled="!selected || !question.trim() || loading" @click="ask">
          <el-icon><Promotion /></el-icon>提问
        </el-button>
      </div>
      <div class="bar-row">
        <el-input v-model="question" type="textarea" :rows="2" resize="none"
                  placeholder="输入自然语言问题，例如：哪个产品销售额最高？"
                  @keydown.enter.exact.prevent="ask" />
      </div>
      <div v-if="sampleQuestions.length" class="hints">
        <span class="hint-label">示例问题：</span>
        <el-button v-for="q in sampleQuestions" :key="q" size="small" text type="primary" @click="question = q">{{ q }}</el-button>
      </div>
    </div>

    <!-- 校验提示（未选表 / 空问题） -->
    <el-alert v-if="validateMsg" :title="validateMsg" type="warning" show-icon :closable="false" class="inline-alert" />

    <!-- 表格来源加载失败 -->
    <el-alert v-if="tablesError && !result && !loading" :title="tablesError" type="error" show-icon :closable="false" class="inline-alert" />

    <!-- 提问加载态 -->
    <div v-if="loading" class="card"><SkeletonLoader variant="table" :rows="5" /></div>

    <!-- 提问错误态（400/404/409 等） -->
    <div v-else-if="error" class="card error-card">
      <div class="error-head"><el-icon><WarningFilled /></el-icon>{{ error.title }}</div>
      <div class="error-body">{{ error.message }}</div>
    </div>

    <!-- 空态 -->
    <div v-else-if="!result" class="card">
      <EmptyState icon="Grid" title="表格问答" desc="选择一张表格并输入自然语言问题，系统将生成只读 SQL 并返回答案、数据表与图表">
        <el-button v-if="!docTables.length && !tables.length && !tablesLoading" @click="loadTables">重新加载</el-button>
      </EmptyState>
    </div>

    <!-- 结果区 -->
    <template v-else>
      <!-- 答案 + 元信息 -->
      <div class="card answer-card">
        <div class="answer-head">
          <span class="answer-label">回答</span>
          <div class="meta-tags">
            <el-tag v-if="isDemo" size="small" type="warning" effect="dark" class="demo-badge">规则降级/演示数据</el-tag>
            <el-tag v-else size="small" type="success" effect="plain">LLM 生成</el-tag>
            <el-tag v-if="result.metrics && result.metrics.elapsed_ms != null" size="small" type="info" effect="plain">耗时 {{ result.metrics.elapsed_ms }} ms</el-tag>
            <el-tag v-if="result.metrics && result.metrics.attempts" size="small" type="info" effect="plain">尝试 {{ result.metrics.attempts }} 次</el-tag>
            <el-tag v-if="result.metrics && result.metrics.tokens" size="small" type="info" effect="plain">{{ result.metrics.tokens }} tokens</el-tag>
          </div>
        </div>
        <div class="answer-body">{{ result.answer }}</div>
        <div v-if="result.metrics && result.metrics.fallback_reason" class="fallback-reason">
          <el-icon><InfoFilled /></el-icon>降级原因：{{ result.metrics.fallback_reason }}
        </div>
        <div v-if="result.metrics && (result.metrics.intent || result.metrics.table_name)" class="intent-line">
          识别意图：{{ result.metrics.intent || '—' }} · 表：{{ result.metrics.table_name || result.metrics.table_id || '—' }}
        </div>
      </div>

      <!-- 数据表 -->
      <div class="card table-card">
        <div class="card-title"><el-icon><Grid /></el-icon>查询结果<span class="count">（{{ result.rows.length }} 行）</span></div>
        <el-table :data="resultRows" size="small" border>
          <el-table-column v-for="col in result.columns" :key="col" :label="col" min-width="120" show-overflow-tooltip>
            <template #default="{ row }"><span class="cell">{{ text(row[col]) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 图表 -->
      <div class="card chart-card">
        <div class="card-title"><el-icon><DataLine /></el-icon>图表视图</div>
        <ResultChart :chart="result.chart || { type: 'table', columns: [], rows: [] }" />
      </div>

      <!-- 生成的 SQL（可折叠） -->
      <div class="card sql-card">
        <el-collapse v-model="sqlOpen">
          <el-collapse-item name="sql">
            <template #title>
              <span class="sql-title"><el-icon><Coin /></el-icon>生成的 SQL</span>
            </template>
            <pre class="sql-code"><code>{{ result.sql || '（本次回答未生成 SQL）' }}</code></pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { Promotion, WarningFilled, InfoFilled, Grid, DataLine, Coin } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import EmptyState from '@/components/EmptyState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import ResultChart from '@/components/ResultChart.vue'

const props = defineProps({ docId: { type: Number, required: true } })
const tables = ref([])
const docTables = ref([])
const tablesLoading = ref(true)
const tablesError = ref('')
const selected = ref('')
const question = ref('')
const loading = ref(false)
const result = ref(null)
const error = ref(null)
const validateMsg = ref('')
const sqlOpen = ref([])
const sampleQuestions = ['哪个产品销售额最高？', '按月统计销售额合计', '列出交换机相关的记录']

const allOptions = computed(() => [...docTables.value, ...tables.value])
const selectedMeta = computed(() => allOptions.value.find((t) => t.key === selected.value) || null)
const isDemo = computed(() =>
  !!result.value && (result.value.source === 'demo' || !!(result.value.metrics && result.value.metrics.fallback_reason)),
)
const resultRows = computed(() => {
  const columns = (result.value && result.value.columns) || []
  return ((result.value && result.value.rows) || []).map((r) =>
    Object.fromEntries(columns.map((c, i) => [c, r[i]])),
  )
})
function text(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
function errorTitle(status, message) {
  if (status === 400) return '请求参数有误（400）'
  if (status === 404) return '表格或文档不存在（404）'
  if (status === 409) return '文档尚未完成解析（409）'
  return '表格问答失败'
}
async function loadTables() {
  tablesLoading.value = true
  tablesError.value = ''
  const jobs = [api.listQaTables().catch(() => [])]
  if (props.docId != null) {
    jobs.push(
      api.getDocument(props.docId)
        .then((d) => (d.chunks || []).filter((c) => c.kind === 'table'))
        .catch(() => []),
    )
  }
  try {
    const [registered, chunks] = await Promise.all(jobs)
    tables.value = (registered || []).map((t) => ({
      key: 'table:' + t.id,
      kind: 'table',
      id: t.id,
      label: `${t.name}（${t.id} · ${t.row_count} 行）`,
      source: t.source,
      rows: t.row_count,
    }))
    docTables.value = (chunks || []).map((c) => ({
      key: 'doc:' + c.id,
      kind: 'doc',
      id: props.docId,
      chunkId: c.id,
      label: `${c.title || '表格块 #' + c.id}${c.page ? ' · 第 ' + c.page + ' 页' : ''}`,
      source: 'doc',
      rows: null,
    }))
    if (!tables.value.length && !docTables.value.length) {
      tablesError.value = '当前没有可查询的表格：文档中没有表格块，且服务端也没有已注册表格'
    }
  } finally {
    tablesLoading.value = false
  }
}
async function ask() {
  validateMsg.value = ''
  if (!selected.value) {
    validateMsg.value = '请先选择要查询的表格'
    return
  }
  const q = question.value.trim()
  if (!q) {
    validateMsg.value = '请输入问题后再提问'
    return
  }
  const meta = selectedMeta.value
  if (!meta) {
    validateMsg.value = '所选表格已失效，请重新选择'
    return
  }
  const body = meta.kind === 'doc'
    ? { question: q, doc_id: meta.id }
    : { question: q, table_id: meta.id }
  loading.value = true
  error.value = null
  try {
    result.value = await api.tableQa(body)
    sqlOpen.value = []
  } catch (e) {
    result.value = null
    error.value = {
      status: e.status || 0,
      title: errorTitle(e.status || 0, e.message),
      message: e.message || '请求失败，请稍后重试',
    }
  } finally {
    loading.value = false
  }
}
onMounted(loadTables)
</script>
<style scoped>
.table-qa-tab { display: flex; flex-direction: column; gap: 14px; }
.qa-bar { display: flex; flex-direction: column; gap: 12px; padding: 18px 20px; }
.bar-row { display: flex; align-items: center; gap: 12px; }
.pick { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.label { font-size: 13px; color: var(--dm-text-muted); font-weight: 600; white-space: nowrap; }
.table-pick { width: 340px; }
.pick-tag { flex-shrink: 0; }
.spacer { flex: 1; }
.hints { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.hint-label { font-size: 12px; color: var(--dm-text-muted); }
.inline-alert { margin-top: 2px; }
.error-card { padding: 18px 20px; display: flex; flex-direction: column; gap: 6px; }
.error-head { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--dm-danger); }
.error-body { font-size: 13px; color: var(--dm-text); word-break: break-all; }
.answer-card { padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; }
.answer-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.answer-label { font-size: 14px; font-weight: 700; color: var(--dm-heading); }
.meta-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.answer-body { font-size: 14px; line-height: 1.75; color: var(--dm-text); background: var(--dm-fill); border-radius: var(--dm-radius-sm); padding: 12px 14px; }
.fallback-reason { display: flex; align-items: flex-start; gap: 6px; font-size: 12.5px; color: var(--dm-warning); background: var(--dm-warning-bg); border: 1px solid var(--dm-warning-border); border-radius: 8px; padding: 8px 10px; }
.intent-line { font-size: 12px; color: var(--dm-text-muted); }
.card-title { display: flex; align-items: center; gap: 6px; font-size: 13.5px; font-weight: 700; color: var(--dm-heading); margin-bottom: 10px; }
.card-title .count { font-weight: 400; color: var(--dm-text-muted); font-size: 12px; }
.cell { font-size: 12.5px; font-variant-numeric: tabular-nums; }
.sql-card :deep(.el-collapse-item__header) { font-size: 13.5px; font-weight: 700; color: var(--dm-heading); }
.sql-title { display: flex; align-items: center; gap: 6px; }
.sql-code { margin: 0; padding: 12px 14px; background: var(--dm-code-bg); color: var(--dm-code-text); border-radius: 8px; font-size: 12.5px; line-height: 1.7; overflow-x: auto; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; white-space: pre-wrap; word-break: break-all; }
@media (max-width: 1280px) {
  .table-pick { width: 100%; }
  .bar-row { flex-wrap: wrap; }
}
</style>
