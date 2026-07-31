<template>
  <div class="task-progress" :class="{ failed: error }">
    <div class="track"><div class="fill" :style="{ width: pct + '%' }"></div></div>
    <div class="meta">
      <span v-if="error" class="err"><el-icon><WarningFilled /></el-icon>{{ error }}</span>
      <span v-else class="msg"><el-icon v-if="running" class="is-loading"><Loading /></el-icon>{{ message || label }}</span>
      <span v-if="running" class="pct">{{ pct }}%</span>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
const props = defineProps({ running: Boolean, progress: { type: Number, default: 0 }, message: { type: String, default: '' }, error: { type: String, default: '' }, label: { type: String, default: '处理中' } })
const pct = computed(() => Math.min(100, Math.max(0, props.progress)))
</script>
<style scoped>
.task-progress { padding: 10px 14px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); }
.task-progress.failed { border-color: var(--dm-danger-border); background: var(--dm-danger-bg); }
.track { height: 4px; border-radius: 2px; background: var(--dm-track); overflow: hidden; }
.fill { height: 100%; border-radius: 2px; background: linear-gradient(90deg, var(--dm-primary), var(--dm-teal)); transition: width .3s ease; }
.meta { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; font-size: 12px; color: var(--dm-text-muted); }
.msg { display: inline-flex; align-items: center; gap: 6px; }
.err { display: inline-flex; align-items: center; gap: 6px; color: var(--dm-danger); }
.pct { font-variant-numeric: tabular-nums; }
</style>
