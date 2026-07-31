<template>
  <div class="skeleton" :class="variant">
    <div v-for="n in rows" :key="n" class="line" :style="{ width: widths[(n - 1) % widths.length] }"></div>
  </div>
</template>
<script setup>
defineProps({ variant: { type: String, default: 'page' }, rows: { type: Number, default: 5 } })
const widths = ['100%', '92%', '96%', '85%', '98%', '88%']
</script>
<style scoped>
.skeleton { display: flex; flex-direction: column; gap: 14px; }
.line { height: 16px; border-radius: 8px; background: linear-gradient(90deg, #e2e8f0 25%, #eef2f7 50%, #e2e8f0 75%); background-size: 200% 100%; animation: dm-breathe 1.2s infinite; }
.skeleton.card .line { height: 120px; }
.skeleton.table .line { height: 40px; }
@keyframes dm-breathe { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
