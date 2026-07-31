<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const navItems = [
  { path: '/', label: '工作台', icon: 'House' },
  { path: '/documents', label: '文档库', icon: 'FolderOpened' },
  { path: '/schemas', label: '抽取 Schema', icon: 'Grid' },
  { path: '/samples', label: '修正样本', icon: 'DataAnalysis' },
  { path: '/settings', label: '设置', icon: 'Setting' },
]
const isActive = (p) => route.path === p || (p !== '/' && route.path.startsWith(p))
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-mark">D</div>
        <div>
          <div class="logo-name">DocMind</div>
          <div class="logo-sub">文档智能助手</div>
        </div>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item" :class="{ active: isActive(item.path) }">
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-foot">v0.1.0 · 求职作品集</div>
    </aside>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell { display: flex; height: 100%; }
.sidebar {
  width: 224px; flex-shrink: 0; background: var(--dm-navy); color: #fff;
  display: flex; flex-direction: column; padding: 20px 14px;
}
.logo { display: flex; gap: 12px; align-items: center; padding: 4px 10px 22px; }
.logo-mark {
  width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, var(--dm-primary), var(--dm-teal));
  display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800; color: #fff;
}
.logo-name { font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.logo-sub { font-size: 11px; color: rgba(255,255,255,.55); }
.nav { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 10px;
  color: rgba(255,255,255,.72); font-size: 14px; transition: all .18s ease;
}
.nav-item:hover { background: rgba(255,255,255,.08); color: #fff; }
.nav-item.active { background: var(--dm-primary); color: #fff; font-weight: 600; }
.sidebar-foot { font-size: 11px; color: rgba(255,255,255,.4); padding: 10px 12px 0; }
.main { flex: 1; overflow-y: auto; min-width: 0; }
</style>
