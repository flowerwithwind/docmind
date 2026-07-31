<template>
  <div class="extract-tab">
    <!-- 未解析引导态 -->
    <div v-if="doc.status !== 'parsed'" class="card">
      <EmptyState icon="Tickets" title="解析完成后才能抽取" desc="DocMind 会先完成版式解析与分块，随后可基于 Schema 做结构化抽取">
        <el-button type="primary" disabled>等待解析完成</el-button>
      </EmptyState>
    </div>

    <template v-else>
      <!-- 加载失败 -->
      <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load" /></div>
      <!-- 加载中 -->
      <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="6" /></div>

      <template v-else>
        <!-- 顶部操作行 -->
        <div class="top-bar card">
          <div class="schema-pick">
            <span class="label">抽取 Schema</span>
            <el-select v-model="schemaId" style="width: 240px" :disabled="taskRunning" @change="onSchemaChange">
              <el-option v-for="s in schemas" :key="s.id" :label="s.name + (s.is_builtin ? '（内置）' : '')" :value="s.id" />
            </el-select>
          </div>
          <el-select v-if="extractions.length" v-model="activeExtId" style="width: 250px" placeholder="历史抽取结果">
            <el-option v-for="e in extractions" :key="e.id" :value="e.id">
              <span class="opt-row">
                <span>{{ schemaName(e.schema_id) }}</span>
                <StatusBadge :value="e.status" map="extraction" />
                <span class="opt-time">{{ formatTime(e.updated_at) }}</span>
              </span>
            </el-option>
          </el-select>
          <div class="spacer"></div>
          <el-button v-if="result" plain :disabled="taskRunning" @click="restartExtract"><el-icon><Refresh /></el-icon>重新抽取</el-button>
          <el-button v-else type="primary" :loading="taskRunning" @click="startExtract"><el-icon><MagicStick /></el-icon>开始抽取</el-button>
        </div>

        <TaskProgress v-if="taskRunning" :running="taskRunning" :progress="progress" :message="message" label="正在结构化抽取…" class="task-line" />
        <TaskProgress v-else-if="taskError" :error="taskError" label="抽取失败" class="task-line" />

        <!-- 抽取结果 -->
        <template v-if="result">
          <div v-if="result.status === 'confirmed'" class="banner success">
            <el-icon><CircleCheck /></el-icon>
            <span>已确认 · 修改过的字段已生成修正样本，可到「修正样本」页导出评测集（{{ formatTime(result.confirmed_at) }}）</span>
          </div>
          <div v-if="result.error" class="banner error"><el-icon><WarningFilled /></el-icon><span>{{ result.error }}</span></div>

          <!-- 概览 -->
          <div class="overview">
            <div class="ov-card">
              <div class="ov-label">整体置信度</div>
              <div class="ov-value" :class="confLevel">{{ avgConfidence }}%</div>
              <div class="ov-track"><div class="ov-fill" :class="confLevel" :style="{ width: avgConfidence + '%' }"></div></div>
            </div>
            <div class="ov-card">
              <div class="ov-label">字段总数</div>
              <div class="ov-value">{{ fieldRows.length }}</div>
              <div class="ov-sub">{{ confirmedCount }} 项缺失 / {{ editedCount }} 项已修改</div>
            </div>
            <div class="ov-card">
              <div class="ov-label">抽取来源</div>
              <div class="ov-value small">{{ result.source === 'llm' ? 'LLM 模型' : '规则引擎' }}</div>
              <div class="ov-sub">{{ result.source === 'llm' ? '大模型结构化输出' : '演示模式 · 正则规则抽取' }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-label">结果状态</div>
              <div class="ov-badge"><StatusBadge :value="result.status" map="extraction" /></div>
              <div class="ov-sub">{{ result.status === 'confirmed' ? '已锁定，重新抽取会新建结果' : '可编辑字段值并确认' }}</div>
            </div>
          </div>

          <!-- 字段结果表 -->
          <div class="card table-card">
            <el-table :data="fieldRows" :row-class-name="rowClass">
              <el-table-column label="字段" min-width="150">
                <template #default="{ row }">
                  <div class="f-label">{{ row.field.label }}</div>
                  <div class="f-key">{{ row.field.key }}<el-tag v-if="row.field.required" size="small" type="danger" effect="plain" class="req">必填</el-tag></div>
                </template>
              </el-table-column>
              <el-table-column label="值（点击编辑）" min-width="220">
                <template #default="{ row }">
                  <FieldCellEditor :field="row.field" :value="row.value" :disabled="result.status === 'confirmed'" @save="(v) => saveField(row.key, v)" />
                </template>
              </el-table-column>
              <el-table-column label="置信度" width="150">
                <template #default="{ row }">
                  <ConfidenceBar v-if="row.confidence != null" :value="row.confidence" />
                  <span v-else class="muted">—（人工修改）</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }"><StatusBadge :value="row.fieldStatus" map="field" /></template>
              </el-table-column>
              <el-table-column label="依据" width="90" align="center">
                <template #default="{ row }">
                  <el-button v-if="row.citations.length" link type="primary" @click="openCite(row)"><el-icon><Link /></el-icon>{{ row.citations.length }} 处</el-button>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="table-foot">
              <span class="muted">来源：{{ result.source === 'llm' ? 'LLM 抽取' : '规则抽取（演示模式）' }}</span>
              <div class="foot-ops">
                <el-button-group>
                  <el-button size="small" @click="doExport('json')"><el-icon><Download /></el-icon>JSON</el-button>
                  <el-button size="small" @click="doExport('excel')"><el-icon><Download /></el-icon>Excel</el-button>
                  <el-button size="small" @click="doExport('markdown')"><el-icon><Download /></el-icon>Markdown</el-button>
                </el-button-group>
                <el-button v-if="result.status === 'draft'" type="primary" :loading="confirming" @click="confirmResult"><el-icon><CircleCheck /></el-icon>确认结果</el-button>
              </div>
            </div>
          </div>
        </template>

        <!-- 未抽取：Schema 字段预览 -->
        <div v-else class="card preview-card">
          <template v-if="currentSchema">
            <div class="preview-head">
              <div>
                <div class="preview-title">{{ currentSchema.name }}</div>
                <div class="preview-desc">{{ currentSchema.description || '选择该 Schema 后开始结构化抽取，抽取结果可编辑、确认并导出。' }}</div>
              </div>
              <el-button type="primary" size="large" :loading="taskRunning" @click="startExtract"><el-icon><MagicStick /></el-icon>开始抽取</el-button>
            </div>
            <el-table :data="currentSchema.fields" class="field-preview">
              <el-table-column label="字段 Key" prop="key" min-width="150">
                <template #default="{ row }"><span class="mono">{{ row.key }}</span></template>
              </el-table-column>
              <el-table-column label="名称" prop="label" min-width="130" />
              <el-table-column label="类型" width="110">
                <template #default="{ row }"><el-tag size="small" effect="plain">{{ TYPE_LABELS[row.type] || row.type }}</el-tag></template>
              </el-table-column>
              <el-table-column label="必填" width="90">
                <template #default="{ row }"><el-tag v-if="row.required" size="small" type="danger">必填</el-tag><span v-else class="muted">—</span></template>
              </el-table-column>
              <el-table-column label="取值约束" min-width="160">
                <template #default="{ row }">
                  <span v-if="row.enum && row.enum.length" class="enum">{{ row.enum.join(' / ') }}</span>
                  <span v-else class="muted">{{ row.description || '—' }}</span>
                </template>
              </el-table-column>
            </el-table>
          </template>
          <EmptyState v-else icon="Grid" title="暂无抽取 Schema" desc="请先到「抽取 Schema」页创建或启用一个 Schema">
            <el-button type="primary" @click="$router.push('/schemas')">去创建 Schema</el-button>
          </EmptyState>
        </div>
      </template>
    </template>

    <!-- 引用抽屉 -->
    <SourceDrawer v-model="drawerVisible" :citation="activeCitation" :chunk="activeChunk" />
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Tickets, Refresh, MagicStick, CircleCheck, WarningFilled, Link, Download } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import { useTask } from '@/composables/useTask'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ConfidenceBar from '@/components/ConfidenceBar.vue'
import FieldCellEditor from '@/components/FieldCellEditor.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import SourceDrawer from '@/components/SourceDrawer.vue'
import { formatTime } from '@/utils/format'

const props = defineProps({ doc: { type: Object, required: true }, data: { type: Object, required: true } })

const TYPE_LABELS = { string: '文本', number: '数值', date: '日期', list: '列表', object: '对象' }
const schemas = ref([])
const extractions = ref([])
const schemaId = ref(null)
const activeExtId = ref(null)
const loading = ref(true)
const loadError = ref('')
const confirming = ref(false)
const drawerVisible = ref(false)
const activeCitation = ref(null)
const activeChunk = ref(null)
const { running: taskRunning, progress, message, error: taskError, run } = useTask()

const currentSchema = computed(() => schemas.value.find((s) => s.id === schemaId.value) || null)
const result = computed(() => extractions.value.find((e) => e.id === activeExtId.value) || null)
const chunkMap = computed(() => {
  const map = {}
  for (const c of props.data.chunks || []) map[c.id] = c
  return map
})
const fieldRows = computed(() => {
  const ext = result.value
  if (!ext || !currentSchema.value) return []
  return currentSchema.value.fields.map((f) => ({
    key: f.key,
    field: f,
    value: ext.data[f.key],
    confidence: ext.confidence[f.key],
    fieldStatus: ext.field_status[f.key] || (ext.data[f.key] == null || ext.data[f.key] === '' ? 'missing' : 'extracted'),
    citations: ext.citations[f.key] || [],
  }))
})
const confValues = computed(() => fieldRows.value.map((r) => r.confidence).filter((v) => v != null))
const avgConfidence = computed(() => {
  if (!confValues.value.length) return 0
  return Math.round((confValues.value.reduce((a, b) => a + b, 0) / confValues.value.length) * 100)
})
const confLevel = computed(() => (avgConfidence.value >= 80 ? 'high' : avgConfidence.value >= 50 ? 'mid' : 'low'))
const editedCount = computed(() => fieldRows.value.filter((r) => r.fieldStatus === 'edited').length)
const confirmedCount = computed(() => fieldRows.value.filter((r) => r.fieldStatus === 'missing').length)

function schemaName(id) {
  const s = schemas.value.find((x) => x.id === id)
  return s ? s.name : 'Schema #' + id
}
function rowClass({ row }) {
  return row.fieldStatus === 'edited' ? 'row-edited' : ''
}
function onSchemaChange() {
  const hit = extractions.value.find((e) => e.schema_id === schemaId.value)
  activeExtId.value = hit ? hit.id : null
}
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [schemaList, extList] = await Promise.all([api.listSchemas(), api.listExtractions(props.doc.id)])
    schemas.value = schemaList
    extractions.value = extList
    if (!schemas.value.length) return
    if (schemaId.value == null || !schemas.value.some((s) => s.id === schemaId.value)) {
      schemaId.value = extList.length ? extList[0].schema_id : schemas.value[0].id
    }
    const hit = extList.find((e) => e.schema_id === schemaId.value)
    activeExtId.value = hit ? hit.id : (extList.length ? extList[extList.length - 1].id : null)
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
async function reloadExtractions() {
  const extList = await api.listExtractions(props.doc.id)
  extractions.value = extList
  if (!activeExtId.value || !extList.some((e) => e.id === activeExtId.value)) {
    const hit = extList.find((e) => e.schema_id === schemaId.value) || extList[extList.length - 1]
    activeExtId.value = hit ? hit.id : null
  }
}
async function startExtract() {
  if (!schemaId.value) return
  taskError.value = ''
  try {
    const body = await api.startExtract(props.doc.id, schemaId.value)
    await run(body.task_id, { onDone: reloadExtractions })
    await reloadExtractions()
    ElMessage.success('抽取完成')
  } catch (e) {
    ElMessage.error(e.message || '抽取失败')
  }
}
async function restartExtract() {
  if (!result.value) return
  try {
    await ElMessageBox.confirm('重新抽取将生成一份新的抽取结果（已确认的旧结果保留为历史），确定继续？', '重新抽取', { type: 'warning', confirmButtonText: '重新抽取' })
  } catch { return }
  taskError.value = ''
  try {
    const body = result.value.status === 'confirmed'
      ? await api.reextract(result.value.id)
      : await api.startExtract(props.doc.id, schemaId.value)
    await run(body.task_id, { onDone: reloadExtractions })
    await reloadExtractions()
    ElMessage.success('重新抽取完成')
  } catch (e) {
    ElMessage.error(e.message || '重新抽取失败')
  }
}
async function saveField(key, value) {
  const ext = result.value
  if (!ext || ext.status === 'confirmed') return
  try {
    const updated = await api.editExtraction(ext.id, { [key]: value })
    const idx = extractions.value.findIndex((e) => e.id === ext.id)
    if (idx >= 0) extractions.value[idx] = updated
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  }
}
async function confirmResult() {
  const ext = result.value
  if (!ext) return
  const edited = fieldRows.value.filter((r) => r.fieldStatus === 'edited').length
  const tip = edited > 0
    ? '确认后 ' + edited + ' 个已修改字段将生成修正样本，用于后续抽取效果评测与优化。确定确认？'
    : '未修改任何字段，确认后将锁定当前抽取结果。确定确认？'
  try {
    await ElMessageBox.confirm(tip, '确认抽取结果', { type: 'warning', confirmButtonText: '确认', cancelButtonText: '再检查一下' })
  } catch { return }
  confirming.value = true
  try {
    const updated = await api.confirmExtraction(ext.id)
    const idx = extractions.value.findIndex((e) => e.id === ext.id)
    if (idx >= 0) extractions.value[idx] = updated
    ElMessage.success('已确认，修正样本已入库')
  } catch (e) {
    ElMessage.error(e.message || '确认失败')
  } finally {
    confirming.value = false
  }
}
function doExport(fmt) {
  if (!result.value) return
  window.open(api.exportExtraction(result.value.id, fmt), '_blank')
}
function openCite(row) {
  if (!row.citations.length) return
  activeCitation.value = row.citations[0]
  activeChunk.value = chunkMap.value[activeCitation.value.chunk_id] || null
  drawerVisible.value = true
}
onMounted(load)
</script>
<style scoped>
.top-bar { display: flex; align-items: center; gap: 14px; padding: 14px 16px; margin-bottom: 14px; flex-wrap: wrap; }
.schema-pick { display: flex; align-items: center; gap: 10px; }
.label { font-size: 13px; font-weight: 600; color: var(--dm-text); }
.spacer { flex: 1; }
.task-line { margin-bottom: 14px; }
.opt-row { display: flex; align-items: center; gap: 8px; }
.opt-time { font-size: 11px; color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.banner { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-radius: var(--dm-radius); margin-bottom: 14px; font-size: 13px; }
.banner.success { background: #e8f7ee; border: 1px solid #bfe3cc; color: var(--dm-success); }
.banner.error { background: #fdecec; border: 1px solid #f3c1c1; color: var(--dm-danger); }
.overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px; }
.ov-card { background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); padding: 16px 18px; }
.ov-label { font-size: 12px; color: var(--dm-text-muted); margin-bottom: 8px; }
.ov-value { font-size: 26px; font-weight: 700; color: var(--dm-text); font-variant-numeric: tabular-nums; line-height: 1.2; }
.ov-value.small { font-size: 20px; }
.ov-value.high { color: var(--dm-success); }
.ov-value.mid { color: var(--dm-warning); }
.ov-value.low { color: var(--dm-danger); }
.ov-sub { font-size: 11.5px; color: var(--dm-text-muted); margin-top: 6px; line-height: 1.5; }
.ov-badge { margin-top: 4px; }
.ov-track { height: 6px; border-radius: 3px; background: #e8edf3; margin-top: 10px; overflow: hidden; }
.ov-fill { height: 100%; border-radius: 3px; transition: width .3s ease; }
.ov-fill.high { background: var(--dm-success); }
.ov-fill.mid { background: var(--dm-warning); }
.ov-fill.low { background: var(--dm-danger); }
.table-card { padding: 8px 12px 12px; }
.f-label { font-weight: 600; color: var(--dm-text); font-size: 13px; }
.f-key { font-size: 11px; color: #9fb3c8; font-variant-numeric: tabular-nums; display: flex; align-items: center; gap: 6px; }
.req { margin-left: 2px; }
.muted { color: #b6c2d2; font-size: 12px; }
.mono { font-variant-numeric: tabular-nums; }
.table-foot { display: flex; align-items: center; justify-content: space-between; padding: 14px 4px 2px; }
.foot-ops { display: flex; align-items: center; gap: 12px; }
.preview-card { padding: 20px 24px; }
.preview-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.preview-title { font-size: 16px; font-weight: 700; color: var(--dm-text); }
.preview-desc { font-size: 12.5px; color: var(--dm-text-muted); margin-top: 4px; line-height: 1.6; max-width: 560px; }
.enum { font-size: 12px; color: var(--dm-primary); }
.field-preview { margin-top: 4px; }
:deep(.row-edited td) { background: #fdf8ee !important; }
</style>