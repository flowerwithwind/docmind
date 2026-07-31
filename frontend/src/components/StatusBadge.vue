<template>
  <span class="status-badge" :class="type">
    <span class="dot" :class="{ spin: spinning }"></span>
    <span v-if="label" class="label">{{ label }}</span>
    <slot />
  </span>
</template>
<script setup>
import { computed } from 'vue'
import { DOC_STATUS, TASK_STATUS, FIELD_STATUS, DIFF_STATUS, SECTION_STATUS, EX_STATUS, statusOf } from '@/utils/format'
const props = defineProps({
  value: { type: String, required: true },
  map: { type: String, default: 'doc' }, // doc | task | field | diff | section | extraction
  spinning: { type: Boolean, default: false },
})
const MAPS = { doc: DOC_STATUS, task: TASK_STATUS, field: FIELD_STATUS, diff: DIFF_STATUS, section: SECTION_STATUS, extraction: EX_STATUS }
const meta = computed(() => statusOf(props.value, MAPS[props.map] || DOC_STATUS))
const type = computed(() => meta.value.type)
const label = computed(() => meta.value.label)
</script>
<style scoped>
.status-badge { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 10px; border-radius: 999px; font-size: 12px; line-height: 1; white-space: nowrap; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.dot.spin { animation: dm-spin 1s linear infinite; }
.status-badge.info { background: var(--dm-fill-strong); color: var(--dm-text-muted); }
.status-badge.success { background: var(--dm-success-bg); color: var(--dm-success); }
.status-badge.warning { background: var(--dm-warning-bg); color: var(--dm-warning); }
.status-badge.danger { background: var(--dm-danger-bg); color: var(--dm-danger); }
.status-badge.primary { background: var(--dm-primary-light); color: var(--dm-primary); }
@keyframes dm-spin { to { transform: rotate(360deg); } }
</style>
