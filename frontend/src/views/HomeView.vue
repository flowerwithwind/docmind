<template>
  <div class="page home">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-grid"></div>
      <div class="hero-body">
        <div class="hero-badge"><el-icon :size="14"><MagicStick /></el-icon>多模态文档智能助手 · DocMind</div>
        <h1>把合同、财报、扫描件，变成<br />能问、能抽、能比、能导出的智能文档</h1>
        <p class="hero-sub">版式感知解析 · 溯源问答 · 结构化抽取 · 双文档对比，一个工作台全部搞定</p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="$router.push('/documents')"><el-icon><FolderOpened /></el-icon>进入文档库</el-button>
          <el-button size="large" plain class="hero-ghost" @click="scrollToSamples"><el-icon><Download /></el-icon>体验演示样例</el-button>
        </div>
        <div class="caps">
          <span v-for="(ok, key) in demo && demo.capabilities ? demo.capabilities : {}" :key="key" class="cap" :class="{ off: !ok }">
            <el-icon :size="12"><CircleCheck v-if="ok" /><Close v-else /></el-icon>{{ capLabel(key) }}{{ ok ? '' : '（降级）' }}
          </span>
        </div>
      </div>
    </section>

    <div v-if="loadError" class="banner error"><el-icon><WarningFilled /></el-icon><span>{{ loadError }}</span><el-button size="small" @click="load">重试</el-button></div>

    <!-- 演示样例 -->
    <section class="block" ref="samplesRef">
      <div class="block-head"><h2>演示样例</h2><span class="block-sub">空库三步加载 → 问答 / 抽取 / 对比 全流程演示</span></div>
      <div v-if="loading" class="grid"><SkeletonLoader v-for="n in 3" :key="n" variant="card" :rows="2" /></div>
      <div v-else class="grid">
        <SampleCard v-for="s in samples" :key="s.kind" :sample="s" :loading="loadingKind === s.kind" :loaded="s.loaded" @load="loadSample(s)" />
      </div>
    </section>

    <!-- 统计 -->
    <section class="block">
      <div class="block-head"><h2>工作台概览</h2></div>
      <div class="stats">
        <StatCard icon="FolderOpened" label="文档总数" :value="stats.docs" tone="primary" />
        <StatCard icon="DocumentChecked" label="已解析文档" :value="stats.parsed" tone="green" />
        <StatCard icon="TrendCharts" label="对比报告" :value="stats.compares" tone="teal" />
        <StatCard icon="DataAnalysis" label="修正样本" :value="stats.samples" tone="orange" />
      </div>
    </section>

    <!-- 最近文档 -->
    <section class="block">
      <div class="block-head"><h2>最近文档</h2><el-button link type="primary" @click="$router.push('/documents')">全部文档 →</el-button></div>
      <div v-if="loading" class="card"><SkeletonLoader :rows="4" /></div>
      <div v-else-if="recent.length" class="recent card">
        <div v-for="doc in recent" :key="doc.id" class="recent-row" @click="$router.push('/documents/' + doc.id)">
          <DocIcon :ext="doc.ext" />
          <div class="info"><div class="name">{{ doc.original_name }}</div><div class="meta">{{ formatSize(doc.size_bytes) }} · {{ formatTime(doc.created_at) }}</div></div>
          <StatusBadge :value="doc.status" />
          <el-icon class="go"><ArrowRight /></el-icon>
        </div>
      </div>
      <div v-else class="card"><EmptyState icon="FolderOpened" title="还没有文档" desc="上传第一份文档，或点击上方演示样例一键体验" /></div>
    </section>

    <!-- 能力说明 -->
    <section class="block">
      <div class="block-head"><h2>核心能力</h2></div>
      <div class="caps-grid">
        <div class="cap-card"><div class="cap-icon blue"><el-icon :size="22"><Document /></el-icon></div><h3>版式感知解析</h3><p>PDF / Word / Excel / 图片多格式解析，标题结构树、表格、图片智能分块</p></div>
        <div class="cap-card"><div class="cap-icon teal"><el-icon :size="22"><ChatDotRound /></el-icon></div><h3>溯源问答</h3><p>检索增强问答，回答逐字流式输出，点击引用即可定位原文位置</p></div>
        <div class="cap-card"><div class="cap-icon orange"><el-icon :size="22"><Tickets /></el-icon></div><h3>抽取校验闭环</h3><p>结构化抽取 + 置信度标注 + 人工修正样本回流，形成可迭代的评测数据</p></div>
      </div>
    </section>

    <footer class="foot">DocMind v0.1.0 · Vue 3 + FastAPI + SQLite · 求职作品集项目</footer>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, FolderOpened, Download, CircleCheck, Close, WarningFilled, DocumentChecked, TrendCharts, DataAnalysis, ArrowRight, Document, ChatDotRound, Tickets } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import { pollTask } from '@/api/http'
import SampleCard from '@/components/SampleCard.vue'
import StatCard from '@/components/StatCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import DocIcon from '@/components/DocIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatSize, formatTime } from '@/utils/format'
const router = useRouter()
const loading = ref(true)
const loadError = ref('')
const demo = ref(null)
const stats = ref({ docs: 0, parsed: 0, compares: 0, samples: 0 })
const recent = ref([])
const loadingKind = ref('')
const samplesRef = ref(null)
const samples = computed(() => (demo.value ? demo.value.samples : []))
const CAP_LABELS = { llm: 'LLM 问答', ocr: 'OCR 解析', embedding: '向量检索' }
function capLabel(key) { return CAP_LABELS[key] || key }
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const info = await api.demoInfo()
    const docs = await api.listDocuments({ page_size: 1 })
    const parsedRes = await api.listDocuments({ status: 'parsed', page_size: 1 })
    const compares = await api.listCompares()
    const samplesRes = await api.listSamples({ page_size: 1 })
    demo.value = info
    stats.value = {
      docs: docs.total || 0,
      parsed: parsedRes.total || 0,
      compares: Array.isArray(compares) ? compares.length : 0,
      samples: samplesRes.total || 0,
    }
    const recentRes = await api.listDocuments({ page_size: 5 })
    recent.value = recentRes.items || []
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
async function loadSample(sample) {
  if (loadingKind.value) return
  loadingKind.value = sample.kind
  try {
    const body = await api.demoLoad(sample.kind)
    if (body.already_loaded) {
      ElMessage.success('样例已加载')
      router.push('/documents/' + body.doc_id)
      return
    }
    ElMessage.info('正在生成并解析演示样例…')
    await pollTask(body.task_id)
    ElMessage.success('样例加载完成')
    load()
    router.push('/documents/' + body.doc_id)
  } catch (e) {
    if (e.message && e.message.includes('409')) ElMessage.warning('该样例正在加载中，请稍候')
    else ElMessage.error(e.message || '加载失败')
  } finally {
    loadingKind.value = ''
  }
}
function scrollToSamples() { samplesRef.value && samplesRef.value.scrollIntoView({ behavior: 'smooth' }) }
onMounted(load)
</script>
<style scoped>
.home { padding-top: 0; }
.hero { position: relative; overflow: hidden; border-radius: 0 0 20px 20px; background: linear-gradient(135deg, #102a43 0%, #14385c 55%, #1f6feb 130%); color: #fff; padding: 56px 48px 48px; margin: 0 -32px 28px; }
.hero-grid { position: absolute; inset: 0; background-image: radial-gradient(rgba(255,255,255,.14) 1px, transparent 1px); background-size: 22px 22px; mask-image: linear-gradient(135deg, rgba(0,0,0,.8), transparent 70%); }
.hero-body { position: relative; max-width: 960px; }
.hero-badge { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); padding: 5px 12px; border-radius: 999px; font-size: 12px; margin-bottom: 18px; }
.hero h1 { font-size: 30px; line-height: 1.35; margin: 0 0 14px; font-weight: 700; letter-spacing: .3px; }
.hero-sub { font-size: 14px; color: rgba(255,255,255,.75); margin: 0 0 26px; }
.hero-actions { display: flex; gap: 12px; margin-bottom: 22px; }
.hero-ghost { background: rgba(255,255,255,.1); border-color: rgba(255,255,255,.3); color: #fff; } .hero-ghost:hover { background: rgba(255,255,255,.18); color: #fff; border-color: rgba(255,255,255,.5); }
.caps { display: flex; gap: 8px; flex-wrap: wrap; }
.cap { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; background: rgba(16,185,129,.16); color: #6ee7b7; padding: 4px 10px; border-radius: 999px; }
.cap.off { background: rgba(255,255,255,.1); color: rgba(255,255,255,.6); }
.banner { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 10px; margin-bottom: 20px; font-size: 13px; }
.banner.error { background: #fdecec; color: var(--dm-danger); border: 1px solid #f3c1c1; }
.block { margin-bottom: 28px; }
.block-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
.block-head h2 { font-size: 18px; margin: 0; color: var(--dm-navy); }
.block-sub { font-size: 12.5px; color: var(--dm-text-muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.recent { overflow: hidden; }
.recent-row { display: flex; align-items: center; gap: 14px; padding: 12px 16px; cursor: pointer; transition: background .15s; }
.recent-row + .recent-row { border-top: 1px solid #f1f5f9; }
.recent-row:hover { background: #f8fafc; }
.info { flex: 1; min-width: 0; }
.name { font-size: 13.5px; font-weight: 600; color: var(--dm-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { font-size: 12px; color: var(--dm-text-muted); margin-top: 2px; font-variant-numeric: tabular-nums; }
.go { color: #b6c2d2; }
.caps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.cap-card { padding: 22px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); transition: box-shadow .15s, transform .15s; }
.cap-card:hover { box-shadow: var(--dm-shadow-lg); transform: translateY(-1px); }
.cap-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 14px; }
.cap-icon.blue { background: rgba(31,111,235,.12); color: var(--dm-primary); }
.cap-icon.teal { background: rgba(14,116,144,.12); color: var(--dm-teal); }
.cap-icon.orange { background: rgba(217,119,6,.12); color: var(--dm-warning); }
.cap-card h3 { margin: 0 0 8px; font-size: 15px; color: var(--dm-text); }
.cap-card p { margin: 0; font-size: 12.5px; color: var(--dm-text-muted); line-height: 1.7; }
.foot { text-align: center; font-size: 12px; color: var(--dm-text-disabled); padding: 12px 0 4px; }
</style>
