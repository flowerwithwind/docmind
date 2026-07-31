<template>
  <div class="conf">
    <div class="track"><div class="fill" :class="level" :style="{ width: pct + '%' }"></div></div>
    <span class="num" :class="level">{{ pct }}%</span>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ value: { type: Number, default: 0 } })
const pct = computed(() => Math.round(Math.min(1, Math.max(0, props.value || 0)) * 100))
const level = computed(() => (props.value >= 0.8 ? 'high' : props.value >= 0.5 ? 'mid' : 'low'))
</script>
<style scoped>
.conf { display: inline-flex; align-items: center; gap: 8px; min-width: 96px; }
.track { width: 64px; height: 6px; border-radius: 3px; background: #e8edf3; overflow: hidden; }
.fill { height: 100%; border-radius: 3px; transition: width .3s ease; }
.fill.high { background: var(--dm-success); }
.fill.mid { background: var(--dm-warning); }
.fill.low { background: var(--dm-danger); }
.num { font-size: 12px; font-variant-numeric: tabular-nums; }
.num.high { color: var(--dm-success); }
.num.mid { color: var(--dm-warning); }
.num.low { color: var(--dm-danger); }
</style>
