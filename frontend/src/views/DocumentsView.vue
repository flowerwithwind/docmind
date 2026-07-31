<template>
  <div class="page">
    <div class="head-row">
      <div><h1 class="page-title">文档库</h1><p class="page-sub">上传与管理你的文档，支持 PDF / Word / Excel / 图片</p></div>
      <el-button type="primary" size="large" @click="dialog = true"><el-icon><Upload /></el-icon>上传文档</el-button>
    </div>

    <div class="toolbar card">
      <el-input v-model="query" placeholder="搜索文档名称…" clearable class="search" @keyup.enter="load(1)" @clear="load(1)"><template #prefix><el-icon><Search /></el-icon></template></el-input>
      <el-select v-model="status" placeholder="状态" clearable class="filter" @change="load(1)">
        <el-option label="待解析" value="uploaded" /><el-option label="解析中" value="parsing" /><el-option label="已解析" value="parsed" /><el-option label="解析失败" value="failed" />
      </el-select>
      <el-select v-model="ext" placeholder="类型" clearable class="filter" @change="load(1)">
        <el-option label="PDF" value=".pdf" /><el-option label="Word" value=".docx" /><el-option label="Excel" value=".xlsx" /><el-option label="图片" value=".png" />
      </el-select>
      <div class="spacer"></div>
      <el-radio-group v-model="view" size="default">
        <el-radio-button value="list"><el-icon><List /></el-icon></el-radio-button>
        <el-radio-button value="card"><el-icon><Grid /></el-icon></el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load(page)" /></div>
    <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="6" /></div>

    <!-- 卡片视图 -->
    <div v-else-if="view === 'card' && items.length" class="doc-grid">
      <div v-for="doc in items" :key="doc.id" class="doc-card" :class="{ failed: doc.status === 'failed' }" @click="open(doc)">
        <div class="doc-head"><DocIcon :ext="doc.ext" size="lg" /><StatusBadge :value="doc.status" /></div>
        <div class="doc-name" :title="doc.original_name">{{ doc.original_name }}</div>
        <div class="doc-meta">{{ formatSize(doc.size_bytes) }} · {{ formatTime(doc.created_at) }}</div>
        <div v-if="doc.parse_error" class="doc-err" :title="doc.parse_error">{{ doc.parse_error }}</div>
        <div class="doc-ops" @click.stop>
          <el-button size="small" type="primary" plain @click="open(doc)">打开</el-button>
          <el-button v-if="doc.status === 'failed'" size="small" @click="reparse(doc)">重试解析</el-button>
          <el-button size="small" type="danger" plain @click="remove(doc)">删除</el-button>
        </div>
      </div>
    </div>

    <!-- 列表视图 -->
    <div v-else-if="view === 'list' && items.length" class="card table-card">
      <el-table :data="items" @row-click="open">
        <el-table-column label="文档" min-width="260">
          <template #default="{ row }">
            <div class="doc-cell"><DocIcon :ext="row.ext" /><div class="dc-info"><div class="dc-name">{{ row.original_name }}</div><div class="dc-sub">{{ row.name }}</div></div></div>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100"><template #default="{ row }"><span class="mono">{{ formatSize(row.size_bytes) }}</span></template></el-table-column>
        <el-table-column label="页数" width="80"><template #default="{ row }"><span class="mono">{{ row.page_count ?? '—' }}</span></template></el-table-column>
        <el-table-column label="状态" width="120"><template #default="{ row }"><StatusBadge :value="row.status" /></template></el-table-column>
        <el-table-column label="上传时间" width="150"><template #default="{ row }"><span class="mono">{{ formatTime(row.created_at) }}</span></template></el-table-column>
        <el-table-column label="操作" width="200" align="right">
          <template #default="{ row }">
            <div class="row-ops" @click.stop>
              <el-button link type="primary" @click="open(row)">打开</el-button>
              <el-button v-if="row.status === 'failed'" link @click="reparse(row)">重试</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />
      </div>
    </div>

    <div v-else class="card"><EmptyState icon="FolderOpened" title="还没有文档" desc="上传 PDF / Word / Excel / 图片，DocMind 会自动完成解析分块">
      <el-button type="primary" @click="dialog = true"><el-icon><Upload /></el-icon>上传第一份文档</el-button>
    </EmptyState></div>

    <!-- 上传弹窗 -->
    <el-dialog v-model="dialog" title="上传文档" width="560px" :close-on-click-modal="false">
      <FileDropzone ref="dropzone" @change="onFilesChange" @error="(msg) => ElMessage.error(msg)" />
      <div v-if="uploading.length" class="upload-list">
        <div v-for="u in uploading" :key="u.name" class="upload-item">
          <span class="u-name">{{ u.name }}</span>
          <el-progress :percentage="u.progress" :status="u.error ? 'exception' : undefined" :stroke-width="6" class="u-bar" />
          <span v-if="u.error" class="u-err">{{ u.error }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :disabled="!selected.length || uploading.length > 0" @click="doUpload">开始上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Search, List, Grid } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import { pollTask } from '@/api/http'
import DocIcon from '@/components/DocIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import FileDropzone from '@/components/FileDropzone.vue'
import { formatSize, formatTime } from '@/utils/format'
const router = useRouter()
const query = ref('')
const status = ref('')
const ext = ref('')
const view = ref('list')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const loadError = ref('')
const dialog = ref(false)
const dropzone = ref(null)
const selected = ref([])
const uploading = reactive([])
async function load(p = 1) {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.listDocuments({ query: query.value, status: status.value, ext: ext.value, page: p, page_size: pageSize })
    items.value = res.items
    total.value = res.total
    page.value = p
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
function onFilesChange(list) { selected.value = list }
async function doUpload() {
  if (!selected.value.length) return
  uploading.splice(0, uploading.length)
  try {
    const results = await api.uploadDocuments(selected.value)
    for (const item of results) {
      const entry = { name: item.document.original_name, progress: 0, error: '' }
      uploading.push(entry)
      ;(async () => {
        try {
          await pollTask(item.task_id, {
            onProgress: (t) => { entry.progress = t.progress || 5 },
          })
          entry.progress = 100
        } catch (e) {
          entry.error = e.message || '解析失败'
        }
      })()
    }
    await Promise.all(uploading.map((u) => new Promise((res, rej) => {
      const iv = setInterval(() => { if (u.progress >= 100 || u.error) { clearInterval(iv); u.error ? rej(new Error(u.error)) : res() } }, 200)
    })))
    ElMessage.success('上传完成')
    dialog.value = false
    if (dropzone.value) dropzone.value.clear()
    selected.value = []
    load(1)
  } catch (e) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.splice(0, uploading.length)
  }
}
function open(doc) {
  if (doc.status === 'parsed' || doc.status === 'failed' || doc.status === 'uploaded') router.push('/documents/' + doc.id)
}
async function reparse(doc) {
  try {
    await ElMessageBox.confirm('将重新解析该文档，确定继续？', '重新解析', { type: 'warning', confirmButtonText: '重新解析' })
  } catch { return }
  try {
    const body = await api.reparseDocument(doc.id)
    ElMessage.info('已开始重新解析')
    await pollTask(body.task_id)
    ElMessage.success('解析完成')
    load(page.value)
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}
async function remove(doc) {
  try {
    await ElMessageBox.confirm('删除后文档与解析结果将不可恢复，确定删除「' + doc.original_name + '」？', '删除文档', { type: 'error', confirmButtonText: '删除' })
  } catch { return }
  try {
    await api.deleteDocument(doc.id)
    ElMessage.success('已删除')
    load(page.value)
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
onMounted(() => load(1))
</script>
<style scoped>
.head-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px; }
.search { width: 280px; }
.filter { width: 130px; }
.spacer { flex: 1; }
.doc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }
.doc-card { padding: 18px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); cursor: pointer; transition: box-shadow .15s, transform .15s, border-color .15s; }
.doc-card:hover { box-shadow: var(--dm-shadow-lg); transform: translateY(-2px); border-color: var(--dm-primary-light); }
.doc-card.failed { border-color: var(--dm-danger-border); }
.doc-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.doc-name { font-size: 14px; font-weight: 600; color: var(--dm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; }
.doc-meta { font-size: 12px; color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.doc-err { margin-top: 8px; font-size: 11.5px; color: var(--dm-danger); background: var(--dm-danger-bg); border-radius: 6px; padding: 6px 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-ops { display: flex; gap: 6px; margin-top: 14px; opacity: 0; transition: opacity .15s; }
.doc-card:hover .doc-ops { opacity: 1; }
.doc-cell { display: flex; align-items: center; gap: 12px; }
.dc-info { min-width: 0; }
.dc-name { font-size: 13.5px; font-weight: 600; color: var(--dm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dc-sub { font-size: 11.5px; color: var(--dm-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-variant-numeric: tabular-nums; font-size: 12.5px; color: var(--dm-text); }
.row-ops { display: flex; gap: 4px; justify-content: flex-end; }
.pager { display: flex; justify-content: flex-end; padding: 14px 4px 2px; }
.table-card { padding: 8px 12px 12px; }
.upload-list { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
.upload-item { display: flex; align-items: center; gap: 12px; }
.u-name { flex: 1; min-width: 0; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-bar { flex: 1; }
.u-err { font-size: 12px; color: var(--dm-danger); }
@media (max-width: 1280px) {
  .doc-grid { grid-template-columns: 1fr; }
  .toolbar { flex-wrap: wrap; }
  .search { width: 100%; }
}
@media (max-width: 768px) {
  .head-row { flex-direction: column; align-items: stretch; gap: 12px; }
  .head-row .el-button { align-self: flex-start; }
}
</style>
