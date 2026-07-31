<template>
  <div class="doc-icon" :class="[color, size]">
    <el-icon :size="iconSize"><component :is="icon" /></el-icon>
    <span class="ext">{{ extText }}</span>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { Document, DocumentCopy, Grid, Picture } from '@element-plus/icons-vue'
const props = defineProps({ ext: { type: String, default: '' }, size: { type: String, default: 'md' } })
const extNorm = computed(() => (props.ext || '').toLowerCase())
const color = computed(() => {
  if (['.pdf'].includes(extNorm.value)) return 'pdf'
  if (['.docx', '.doc', '.docm'].includes(extNorm.value)) return 'word'
  if (['.xlsx', '.xls', '.csv'].includes(extNorm.value)) return 'excel'
  if (['.png', '.jpg', '.jpeg', '.webp', '.gif'].includes(extNorm.value)) return 'image'
  return 'plain'
})
const icon = computed(() => {
  if (extNorm.value === '.pdf') return Document
  if (['.docx', '.doc', '.docm'].includes(extNorm.value)) return DocumentCopy
  if (['.xlsx', '.xls', '.csv'].includes(extNorm.value)) return Grid
  if (['.png', '.jpg', '.jpeg', '.webp', '.gif'].includes(extNorm.value)) return Picture
  return Document
})
const extText = computed(() => (props.ext || '').replace('.', '').toUpperCase().slice(0, 4))
const iconSize = computed(() => (props.size === 'lg' ? 26 : 18))
</script>
<style scoped>
.doc-icon { position: relative; display: inline-flex; align-items: center; justify-content: center; border-radius: 10px; color: var(--dm-on-dark); font-weight: 700; }
.doc-icon.md { width: 44px; height: 44px; }
.doc-icon.lg { width: 56px; height: 56px; border-radius: 12px; }
.ext { position: absolute; bottom: 3px; right: 5px; font-size: 8px; letter-spacing: .2px; opacity: .92; }
.doc-icon.pdf { background: linear-gradient(135deg, #f87171, #dc2626); }
.doc-icon.word { background: linear-gradient(135deg, #60a5fa, #1f6feb); }
.doc-icon.excel { background: linear-gradient(135deg, #4ade80, #16a34a); }
.doc-icon.image { background: linear-gradient(135deg, #c084fc, #7c3aed); }
.doc-icon.plain { background: linear-gradient(135deg, #94a3b8, #64748b); }
</style>
