<template>
  <div class="chunk" :class="{ active }" @click="$emit('click')">
    <div class="head">
      <span v-if="chunk.page != null" class="page">{{ chunk.page }}</span>
      <el-icon :size="13" class="kind"><component :is="kindIcon" /></el-icon>
      <span class="section">{{ chunk.section_path || chunk.title || '正文' }}</span>
      <span class="chars">{{ chunk.char_count }} 字</span>
    </div>
    <div v-if="chunk.kind === 'image' && chunk.image_path" class="img">
      <img :src="imageUrl" :alt="chunk.section_path || '图片'" />
    </div>
    <div v-else-if="chunk.kind === 'table'" class="body">
      <MarkdownView :content="chunk.content" />
    </div>
    <pre v-else class="body pre">{{ chunk.content }}</pre>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { Document, Grid, Picture } from '@element-plus/icons-vue'
import MarkdownView from '@/components/MarkdownView.vue'
const props = defineProps({ chunk: { type: Object, required: true }, active: Boolean })
defineEmits(['click'])
const kindIcon = computed(() => (props.chunk.kind === 'table' ? Grid : props.chunk.kind === 'image' ? Picture : Document))
const imageUrl = computed(() => props.chunk.image_path ? '/api/media/images/' + props.chunk.image_path : '')
</script>
<style scoped>
.chunk { border: 1px solid var(--dm-border); border-radius: var(--dm-radius); background: var(--dm-card); transition: border-color .15s ease, box-shadow .15s ease; }
.chunk:hover { border-color: var(--dm-primary); box-shadow: var(--dm-shadow); }
.chunk.active { border-color: var(--dm-primary); box-shadow: 0 0 0 3px var(--dm-ring-primary); }
.head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--dm-fill-strong); font-size: 12px; color: var(--dm-text-muted); }
.page { background: var(--dm-primary); color: var(--dm-on-dark); border-radius: 5px; font-size: 10px; padding: 1px 6px; font-variant-numeric: tabular-nums; }
.kind { color: var(--dm-primary); }
.section { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chars { font-variant-numeric: tabular-nums; }
.body { padding: 10px 12px; font-size: 13px; line-height: 1.7; }
.pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; }
.img { padding: 10px 12px; }
.img img { max-width: 100%; max-height: 320px; border-radius: 8px; border: 1px solid var(--dm-border); }
</style>
