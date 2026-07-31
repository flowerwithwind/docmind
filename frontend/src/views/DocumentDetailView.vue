<template>
  <div class="page detail-page">
    <!-- 加载态 -->
    <div v-if="loading" class="card"><SkeletonLoader variant="table" :rows="6" /></div>
    <!-- 错误态 -->
    <div v-else-if="loadError" class="card"><ErrorState :message="loadError" @retry="load" /></div>

    <template v-else-if="doc">
      <!-- 文档信息头 -->
      <div class="head-row">
        <el-button circle @click="$router.push('/documents')"><el-icon><ArrowLeft /></el-icon></el-button>
        <DocIcon :ext="doc.ext" size="lg" />
        <div class="doc-info">
          <div class="doc-name" :title="doc.original_name">{{ doc.original_name }}</div>
          <div class="doc-meta">
            {{ formatSize(doc.size_bytes) }} · {{ formatTime(doc.created_at) }}
            <template v-if="doc.page_count != null"> · {{ doc.page_count }} 页</template>
            <template v-if="doc.char_count != null"> · {{ doc.char_count.toLocaleString() }} 字符</template>
            <template v-if="doc.chunk_count != null"> · {{ doc.chunk_count }} 分块</template>
          </div>
        </div>
        <div class="spacer"></div>
        <StatusBadge :value="doc.status" />
        <el-button type="danger" plain @click="remove"><el-icon><Delete /></el-icon>删除文档</el-button>
      </div>

      <!-- 四页签 -->
      <el-tabs v-model="tab" class="detail-tabs">
        <el-tab-pane label="解析预览" name="preview" lazy>
          <PreviewTab :doc="doc" :data="data" @reload="load" />
        </el-tab-pane>
        <el-tab-pane label="问答" name="qa" lazy>
          <QaTab :doc-id="doc.id" />
        </el-tab-pane>
        <el-tab-pane label="结构化抽取" name="extract" lazy>
          <ExtractTab :doc="doc" :data="data" />
        </el-tab-pane>
        <el-tab-pane label="文档对比" name="compare" lazy>
          <CompareTab :doc="doc" @goto-extract="tab = 'extract'" />
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 不存在态 -->
    <div v-else class="card"><ErrorState message="文档不存在或已被删除" @retry="load" /></div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Delete } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import DocIcon from '@/components/DocIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import ErrorState from '@/components/ErrorState.vue'
import PreviewTab from '@/views/detail/PreviewTab.vue'
import QaTab from '@/views/detail/QaTab.vue'
import ExtractTab from '@/views/detail/ExtractTab.vue'
import CompareTab from '@/views/detail/CompareTab.vue'
import { formatSize, formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const doc = ref(null)
const data = ref({ pages: [], tree: null, chunks: [] })
const loading = ref(true)
const loadError = ref('')
const tab = ref('preview')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.getDocument(route.params.id)
    doc.value = res.document
    data.value = { pages: res.pages || [], tree: res.tree || null, chunks: res.chunks || [] }
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
async function remove() {
  if (!doc.value) return
  try {
    await ElMessageBox.confirm('删除后文档、解析结果与抽取记录将不可恢复，确定删除「' + doc.value.original_name + '」？', '删除文档', {
      type: 'error', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await api.deleteDocument(doc.value.id)
    ElMessage.success('已删除')
    router.push('/documents')
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
onMounted(load)
</script>
<style scoped>
.head-row { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.doc-info { min-width: 0; }
.doc-name { font-size: 17px; font-weight: 700; color: var(--dm-heading); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-meta { font-size: 12px; color: var(--dm-text-muted); margin-top: 3px; font-variant-numeric: tabular-nums; }
.spacer { flex: 1; }
.detail-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background: var(--dm-border); }
.detail-tabs :deep(.el-tabs__item) { font-size: 14px; }
.detail-tabs :deep(.el-tabs__item.is-active) { color: var(--dm-primary); font-weight: 600; }
.detail-tabs :deep(.el-tabs__active-bar) { background: var(--dm-primary); height: 2.5px; }
@media (max-width: 1280px) {
  .head-row { flex-wrap: wrap; }
  .doc-name { font-size: 15px; }
}
</style>