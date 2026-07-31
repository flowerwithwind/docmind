<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Expand, Fold, Moon, Operation, Sunny } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const collapsed = ref(false)
const { isDark, meta, cycle } = useTheme()

const navItems = [
  { path: '/', label: '工作台', icon: 'House' },
  { path: '/documents', label: '文档库', icon: 'FolderOpened' },
  { path: '/schemas', label: '抽取 Schema', icon: 'Grid' },
  { path: '/samples', label: '修正样本', icon: 'DataAnalysis' },
  { path: '/settings', label: '设置', icon: 'Setting' },
]
const isActive = (p) => route.path === p || (p !== '/' && route.path.startsWith(p))
const themeIcon = computed(() => (meta.value.value === 'dark' ? Moon : meta.value.value === 'light' ? Sunny : Operation))
const themeTip = computed(() => '主题：' + meta.value.label + '（点击切换）')
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="logo">
        <div class="logo-mark">D</div>
        <div class="logo-text">
          <div class="logo-name">DocMind</div>
          <div class="logo-sub">文档智能助手</div>
        </div>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item" :class="{ active: isActive(item.path) }" :title="item.label">
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-foot">
        <span class="foot-text">v1.1.0 · 求职作品集</span>
        <button class="foot-btn btn-collapse" :title="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="collapsed = !collapsed">
          <el-icon :size="15"><Expand v-if="collapsed" /><Fold v-else /></el-icon>
        </button>
        <button class="foot-btn" :title="themeTip" @click="cycle">
          <el-icon :size="15"><component :is="themeIcon" /></el-icon>
        </button>
      </div>
    </aside>
    <main class="main">
      <RouterView v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.app-shell { display: flex; height: 100%; }
.sidebar {
  width: var(--sidebar-w, 220px);
  flex-shrink: 0;
  background: var(--dm-navy);
  color: var(--dm-on-dark);
  display: flex; flex-direction: column;
  padding: 20px 14px;
  overflow: hidden;
  transition: width .2s ease;
  z-index: 100;
}
.sidebar.collapsed { --sidebar-w: 64px; --sidebar-label: none; }

.logo { display: flex; gap: 12px; align-items: center; padding: 4px 10px 22px; white-space: nowrap; }
.logo-mark {
  width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, var(--dm-primary), var(--dm-accent));
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 800; color: var(--dm-on-dark);
}
.logo-text { display: var(--sidebar-label, block); }
.logo-name { font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.logo-sub { font-size: 11px; color: var(--dm-on-dark-faint); }

.nav { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.nav-item {
  position: relative;
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: 10px;
  border-left: 3px solid transparent;
  color: var(--dm-on-dark-muted); font-size: 14px;
  transition: all .18s ease; white-space: nowrap;
}
.nav-label { display: var(--sidebar-label, block); }
.nav-item:hover { background: var(--dm-on-dark-hover); color: var(--dm-on-dark); }
.nav-item.active { background: var(--dm-primary-light); color: var(--dm-primary); border-left-color: var(--dm-primary); font-weight: 600; }

.sidebar-foot { display: flex; align-items: center; gap: 6px; padding: 10px 8px 0; }
.foot-text { display: var(--sidebar-label, block); flex: 1; font-size: 11px; color: var(--dm-on-dark-weak); white-space: nowrap; overflow: hidden; }
.foot-btn {
  width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0;
  border: 1px solid var(--dm-on-dark-border);
  background: transparent; color: var(--dm-on-dark-muted);
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s ease;
}
.foot-btn:hover { background: var(--dm-on-dark-hover); color: var(--dm-on-dark); }

.main { flex: 1; overflow-y: auto; min-width: 0; }

/* 收起态（手动） */
.sidebar.collapsed .logo { justify-content: center; padding: 4px 0 18px; }
.sidebar.collapsed .nav-item { justify-content: center; padding: 10px 0; }
.sidebar.collapsed .sidebar-foot { justify-content: center; }

/* 1280px 以下自动收起为图标栏（§8.2 响应式） */
@media (max-width: 1280px) {
  .sidebar { --sidebar-w: 64px; --sidebar-label: none; }
  .sidebar .logo { justify-content: center; padding: 4px 0 18px; }
  .sidebar .nav-item { justify-content: center; padding: 10px 0; }
  .sidebar .sidebar-foot { justify-content: center; }
  .sidebar .btn-collapse { display: none; }
}
</style>
