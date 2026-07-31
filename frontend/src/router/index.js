import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { title: '工作台' } },
  { path: '/documents', name: 'documents', component: () => import('@/views/DocumentsView.vue'), meta: { title: '文档库' } },
  { path: '/documents/:id', name: 'document-detail', component: () => import('@/views/DocumentDetailView.vue'), meta: { title: '文档详情' } },
  { path: '/schemas', name: 'schemas', component: () => import('@/views/SchemasView.vue'), meta: { title: '抽取 Schema' } },
  { path: '/samples', name: 'samples', component: () => import('@/views/SamplesView.vue'), meta: { title: '修正样本' } },
  { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: '设置' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || ''} · DocMind`
})

export default router
