<template>
  <div class="error">
    <div class="art"><el-icon :size="40"><WarningFilled /></el-icon></div>
    <div class="title">加载失败</div>
    <div class="desc">{{ message || '发生未知错误，请重试' }}</div>
    <div class="actions">
      <el-button type="primary" @click="$emit('retry')"><el-icon><Refresh /></el-icon>重试</el-button>
      <el-button @click="$router.back()">返回</el-button>
    </div>
  </div>
</template>
<script setup>
import { WarningFilled, Refresh } from '@element-plus/icons-vue'
defineProps({ message: { type: String, default: '' } })
defineEmits(['retry'])
</script>
<style scoped>
.error { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 64px 24px; text-align: center; }
.art { width: 96px; height: 96px; border-radius: 50%; background: var(--dm-danger-bg); color: var(--dm-danger); display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.desc { font-size: 13px; color: var(--dm-text-muted); max-width: 480px; line-height: 1.6; margin-bottom: 20px; word-break: break-all; }
.actions { display: flex; gap: 10px; }
</style>
