<template>
  <el-drawer v-model="visible" title="原文定位" size="480px" :append-to-body="true">
    <div v-if="citation" class="source">
      <div class="path">
        <el-icon><Collection /></el-icon>
        <span class="path-text">{{ citation.section || '正文' }}</span>
        <span v-if="citation.page != null" class="page">第 {{ citation.page }} 页</span>
      </div>
      <div class="block" v-html="highlighted"></div>
      <div v-if="!chunk" class="muted">未找到对应原文块（chunk #{{ citation.chunk_id }}）</div>
    </div>
    <div v-else class="muted">请先点击回答中的引用角标</div>
  </el-drawer>
</template>
<script setup>
import { computed } from 'vue'
import { Collection } from '@element-plus/icons-vue'
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  citation: { type: Object, default: null },
  chunk: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
function escapeHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
const highlighted = computed(() => {
  const content = props.chunk ? props.chunk.content : (props.citation ? props.citation.snippet : '')
  const snippet = props.citation ? props.citation.snippet || '' : ''
  const text = escapeHtml(content)
  if (!snippet) return '<pre>' + text + '</pre>'
  const esc = escapeHtml(snippet)
  const idx = text.indexOf(esc)
  if (idx < 0) return '<pre>' + text + '</pre>'
  return '<pre>' + text.slice(0, idx) + '<mark>' + esc + '</mark>' + text.slice(idx + esc.length) + '</pre>'
})
</script>
<style scoped>
.source { display: flex; flex-direction: column; gap: 16px; }
.path { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--dm-text); font-weight: 600; }
.path-text { flex: 1; }
.page { font-size: 11px; background: var(--dm-primary-light); color: var(--dm-primary); padding: 2px 8px; border-radius: 999px; font-variant-numeric: tabular-nums; }
.block pre { margin: 0; background: var(--dm-fill); border: 1px solid var(--dm-border); border-radius: 10px; padding: 14px; font-family: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.block mark { background: var(--dm-mark-bg); color: var(--dm-mark-text); padding: 0 2px; border-radius: 3px; }
.muted { color: var(--dm-text-muted); font-size: 13px; padding: 12px 0; }
</style>
