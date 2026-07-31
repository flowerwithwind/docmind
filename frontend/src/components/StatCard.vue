<template>
  <div class="stat-card">
    <div class="icon" :style="{ background: iconBg }"><el-icon :size="20"><component :is="icon" /></el-icon></div>
    <div class="body">
      <div class="num">{{ value }}</div>
      <div class="label">{{ label }}</div>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ icon: { type: [Object, String], required: true }, label: String, value: [Number, String], tone: { type: String, default: 'primary' } })
const tones = { primary: 'var(--dm-tint-primary)', teal: 'var(--dm-tint-teal)', green: 'var(--dm-tint-green)', orange: 'var(--dm-tint-orange)', purple: 'var(--dm-tint-purple)' }
const iconBg = computed(() => tones[props.tone] || tones.primary)
</script>
<style scoped>
.stat-card { display: flex; align-items: center; gap: 14px; min-width: 200px; padding: 18px 20px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); transition: box-shadow .15s ease, transform .15s ease; }
.stat-card:hover { box-shadow: var(--dm-shadow-lg); transform: translateY(-1px); }
.icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: var(--dm-primary); flex-shrink: 0; }
.num { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.1; color: var(--dm-text); }
.label { font-size: 13px; color: var(--dm-text-muted); margin-top: 2px; }
</style>
