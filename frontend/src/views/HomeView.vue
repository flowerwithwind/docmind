<template>
  <div class="page">
    <h1 class="page-title">工作台</h1>
    <p class="page-sub">DocMind · 多模态文档智能助手（开发中，界面将在 M6 完成）</p>
    <div class="card card-pad placeholder">
      <el-icon :size="40" color="#1f6feb"><Document /></el-icon>
      <p>把合同、财报、扫描件变成「能问、能抽、能改、能导出」的智能文档</p>
    </div>
  </div>
</template>
<script setup>
import { Document } from '@element-plus/icons-vue'
</script>

<style scoped>
.placeholder { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 60px 24px; color: var(--dm-text-muted); text-align: center; }
</style>
