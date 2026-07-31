<template>
  <div class="sample-card" :class="{ loaded }">
    <div class="icon-box" :class="tone"><el-icon :size="26"><component :is="icon" /></el-icon></div>
    <div class="info">
      <div class="name">{{ sample.name }}</div>
      <div class="hint">{{ sample.hint }}</div>
    </div>
    <el-button :type="loaded ? 'success' : 'primary'" :loading="loading" :plain="loaded" @click="$emit('load')">
      {{ loading ? '加载中…' : loaded ? '已加载 · 打开' : '一键加载' }}
    </el-button>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { Document, Files, TrendCharts } from '@element-plus/icons-vue'
const props = defineProps({ sample: { type: Object, required: true }, loading: Boolean, loaded: Boolean })
defineEmits(['load'])
const icon = computed(() => (props.sample.kind === 'financial' ? TrendCharts : props.sample.kind === 'contract_v2' ? Files : Document))
const tone = computed(() => (props.sample.kind === 'financial' ? 'teal' : props.sample.kind === 'contract_v2' ? 'orange' : 'blue'))
</script>
<style scoped>
.sample-card { display: flex; align-items: center; gap: 16px; padding: 18px 20px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); transition: box-shadow .15s ease, transform .15s ease; }
.sample-card:hover { box-shadow: var(--dm-shadow-lg); transform: translateY(-1px); }
.sample-card.loaded { border-color: #bfe3cc; }
.icon-box { width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.icon-box.blue { background: rgba(31,111,235,.12); color: var(--dm-primary); }
.icon-box.teal { background: rgba(14,116,144,.12); color: var(--dm-teal); }
.icon-box.orange { background: rgba(217,119,6,.12); color: var(--dm-warning); }
.info { flex: 1; min-width: 0; }
.name { font-size: 15px; font-weight: 600; color: var(--dm-text); margin-bottom: 4px; }
.hint { font-size: 12px; color: var(--dm-text-muted); line-height: 1.5; }
</style>
