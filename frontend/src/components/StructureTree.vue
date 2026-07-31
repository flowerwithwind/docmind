<template>
  <div class="tree">
    <div v-if="!tree || !tree.children || !tree.children.length" class="tree-empty">暂无章节结构</div>
    <div v-for="node in visibleNodes" :key="node.key" class="node" :class="{ active: node.key === activeKey }"
         :style="{ paddingLeft: 10 + (node.depth - 1) * 16 + 'px' }" @click="$emit('select', node)">
      <el-icon v-if="node.children && node.children.length" :size="12" class="chevron" :class="{ open: node.expanded }" @click.stop="toggle(node.key)"><ArrowRight /></el-icon>
      <span v-else class="leaf-dot"></span>
      <span class="title" :title="node.title">{{ node.title }}</span>
      <span v-if="node.chunk_ids.length" class="count">{{ node.chunk_ids.length }}</span>
      <span v-if="node.page != null" class="page">P{{ node.page }}</span>
    </div>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
const props = defineProps({ tree: { type: Object, default: null }, activeKey: { type: String, default: '' } })
defineEmits(['select'])
const collapsed = ref(new Set())
function toggle(key) {
  const next = new Set(collapsed.value)
  if (next.has(key)) next.delete(key); else next.add(key)
  collapsed.value = next
}
const visibleNodes = computed(() => {
  const out = []
  const walk = (node, depth, parentKey) => {
    if (!node) return
    const key = parentKey ? parentKey + '/' + node.title : node.title
    const children = node.children || []
    const expanded = !collapsed.value.has(key)
    out.push({ ...node, key, depth, expanded, children })
    if (children.length && expanded) {
      for (const c of children) walk(c, depth + 1, key)
    }
  }
  const root = props.tree || { title: '文档', children: [] }
  for (const c of root.children || []) walk(c, 1, '')
  return out
})
watch(() => props.tree, () => { collapsed.value = new Set() })
defineExpose({ toggle })
</script>
<style scoped>
.tree { font-size: 13px; }
.node { display: flex; align-items: center; gap: 6px; padding: 7px 10px; border-radius: 8px; cursor: pointer; color: var(--dm-text); border-left: 3px solid transparent; }
.node:hover { background: var(--dm-fill); }
.node.active { background: var(--dm-primary-light); color: var(--dm-primary); border-left-color: var(--dm-primary); font-weight: 600; }
.chevron { transition: transform .15s ease; color: var(--dm-text-muted); flex-shrink: 0; }
.chevron.open { transform: rotate(90deg); }
.leaf-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--dm-border-strong); flex-shrink: 0; margin-left: 3px; }
.title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { font-size: 10px; background: var(--dm-fill-strong); color: var(--dm-text-muted); border-radius: 999px; padding: 1px 6px; font-variant-numeric: tabular-nums; }
.page { font-size: 10px; color: var(--dm-primary); font-variant-numeric: tabular-nums; }
.tree-empty { padding: 20px 12px; color: var(--dm-text-muted); font-size: 12px; text-align: center; }
</style>
