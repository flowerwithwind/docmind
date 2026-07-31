<template>
  <div class="empty">
    <div class="art"><el-icon :size="44"><component :is="icon" /></el-icon></div>
    <div class="title">{{ title }}</div>
    <div class="desc">{{ desc }}</div>
    <div v-if="$slots.default" class="action"><slot /></div>
  </div>
</template>
<script setup>
import { Document } from '@element-plus/icons-vue'
defineProps({ icon: { type: [Object, String], default: Document }, title: { type: String, default: '暂无数据' }, desc: { type: String, default: '' } })
</script>
<style scoped>
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 64px 24px; text-align: center; }
.art { width: 96px; height: 96px; border-radius: 50%; background: #eef3f9; color: #9fb3c8; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.title { font-size: 16px; font-weight: 600; color: var(--dm-text); margin-bottom: 6px; }
.desc { font-size: 13px; color: var(--dm-text-muted); max-width: 420px; line-height: 1.6; margin-bottom: 16px; }
</style>
