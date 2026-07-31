<template>
  <div class="preview-tab">
    <!-- 未解析/失败态 -->
    <div v-if="doc.status !== 'parsed'" class="card">
      <ErrorState v-if="doc.status === 'failed'" :message="doc.parse_error || '解析失败'" @retry="reparse" />
      <EmptyState v-else icon="Timer" title="文档尚未解析" desc="解析任务正在排队或尚未开始，稍等片刻后刷新；也可以手动触发重新解析">
        <el-button type="primary" @click="reparse">重新解析</el-button>
      </EmptyState>
    </div>

    <div v-else class="preview-body">
      <div class="stats-row">
        <StatCard icon="Document" label="页数" :value="doc.page_count ?? '—'" tone="primary" />
        <StatCard icon="Files" label="字符数" :value="doc.char_count ?? '—'" tone="teal" />
        <StatCard icon="Grid" label="分块数" :value="doc.chunk_count ?? '—'" tone="green" />
        <div class="spacer"></div>
        <el-button @click="reparse"><el-icon><Refresh /></el-icon>重新解析</el-button>
      </div>
      <div class="split">
        <aside class="tree-panel">
          <div class="panel-title">章节结构</div>
          <StructureTree :tree="tree" :active-key="activeKey" @select="onSelect" />
        </aside>
        <div class="chunks-panel">
          <template v-for="(group, gi) in pageGroups" :key="gi">
            <div class="page-sep"><span>第 {{ group.page }} 页</span></div>
            <ChunkBlock v-for="c in group.chunks" :id="'chunk-' + c.seq" :key="c.id" :chunk="c" :active="activeChunk === c.seq" @click="activeChunk = c.seq" />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Files, Grid, Refresh, Timer } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import StatCard from '@/components/StatCard.vue'
import StructureTree from '@/components/StructureTree.vue'
import ChunkBlock from '@/components/ChunkBlock.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
const props = defineProps({ doc: { type: Object, required: true }, data: { type: Object, required: true } })
const emit = defineEmits(['reload'])
const tree = computed(() => props.data.tree)
const chunks = computed(() => props.data.chunks || [])
const activeKey = ref('')
const activeChunk = ref(null)
const pageGroups = computed(() => {
  const map = {}
  for (const c of chunks.value) {
    const page = c.page != null ? c.page : 1
    if (!map[page]) map[page] = { page, chunks: [] }
    map[page].chunks.push(c)
  }
  return Object.values(map)
})
function onSelect(node) {
  activeKey.value = node.key
  if (node.chunk_ids && node.chunk_ids.length) {
    const seq = node.chunk_ids[0]
    activeChunk.value = seq
    const el = document.getElementById('chunk-' + seq)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setTimeout(() => { activeChunk.value = null }, 1500)
    }
  }
}
async function reparse() {
  try {
    await ElMessageBox.confirm('重新解析将重建结构树与分块，确定继续？', '重新解析', { type: 'warning', confirmButtonText: '重新解析' })
  } catch { return }
  try {
    const body = await api.reparseDocument(props.doc.id)
    ElMessage.info('已开始重新解析')
    await api.pollTask(body.task_id)
    ElMessage.success('解析完成')
    emit('reload')
  } catch (e) {
    ElMessage.error(e.message || '解析失败')
  }
}
</script>
<style scoped>
.stats-row { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; }
.spacer { flex: 1; }
.split { display: flex; gap: 16px; align-items: flex-start; }
.tree-panel { width: 260px; flex-shrink: 0; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); padding: 12px; position: sticky; top: 16px; max-height: calc(100vh - 140px); overflow-y: auto; }
.panel-title { font-size: 13px; font-weight: 600; color: var(--dm-text); padding: 4px 8px 10px; border-bottom: 1px solid #f1f5f9; margin-bottom: 8px; }
.chunks-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.page-sep { display: flex; align-items: center; gap: 10px; margin: 6px 0 2px; font-size: 12px; font-weight: 600; color: var(--dm-primary); }
.page-sep::after { content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, #dbe7f7, transparent); }
</style>
