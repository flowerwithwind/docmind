<template>
  <div class="page">
    <div class="head-row">
      <div><h1 class="page-title">设置</h1><p class="page-sub">模型与检索配置 · 危险操作区</p></div>
    </div>

    <!-- 能力状态 -->
    <div v-if="!loading && !loadError" class="cap-row">
      <div v-for="(ok, key) in capabilities" :key="key" class="cap-chip" :class="{ ok }">
        <el-icon :size="14"><CircleCheck v-if="ok" /><Close v-else /></el-icon>
        {{ capLabel(key) }}<span v-if="!ok">（未启用）</span>
      </div>
    </div>

    <!-- 状态区 -->
    <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load" /></div>
    <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="6" /></div>

    <template v-else>
      <!-- 模型设置 -->
      <div class="card block">
        <div class="card-title"><div class="ct-icon blue"><el-icon><Cpu /></el-icon></div><div><div class="ct-name">模型设置</div><div class="ct-sub">问答、抽取与对比的 LLM 配置</div></div></div>
        <div class="form-grid">
          <div class="form-item">
            <label>供应商预设</label>
            <el-select v-model="preset" @change="applyPreset">
              <el-option label="DeepSeek" value="deepseek" />
              <el-option label="OpenAI" value="openai" />
              <el-option label="通义千问（兼容模式）" value="dashscope" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </div>
          <div class="form-item">
            <label>Base URL</label>
            <el-input v-model="modelForm.base_url" placeholder="https://api.deepseek.com/v1" />
          </div>
          <div class="form-item">
            <label>API Key</label>
            <el-input v-model="modelForm.api_key" type="password" show-password :placeholder="hasApiKey ? '已配置（留空保持不变）' : 'sk-…'" />
          </div>
          <div class="form-item">
            <label>模型名</label>
            <el-input v-model="modelForm.model" placeholder="deepseek-chat" />
          </div>
          <div class="form-item">
            <label>Temperature：{{ modelForm.temperature }}</label>
            <el-slider v-model="modelForm.temperature" :min="0" :max="1" :step="0.05" show-input :show-input-controls="false" />
          </div>
          <div class="form-item">
            <label>Max Tokens：{{ modelForm.max_tokens }}</label>
            <el-slider v-model="modelForm.max_tokens" :min="512" :max="8192" :step="256" show-input :show-input-controls="false" />
          </div>
          <div class="form-item full">
            <label>Embedding 模型</label>
            <el-input v-model="modelForm.embedding_model" placeholder="text-embedding-3-small" />
          </div>
        </div>
        <div class="card-foot">
          <el-button :loading="testing" @click="testModel"><el-icon><Connection /></el-icon>测试连接</el-button>
          <div class="spacer"></div>
          <el-button type="primary" :loading="savingModel" @click="saveModel"><el-icon><Check /></el-icon>保存模型设置</el-button>
        </div>
      </div>

      <!-- 检索设置 -->
      <div class="card block">
        <div class="card-title"><div class="ct-icon teal"><el-icon><Search /></el-icon></div><div><div class="ct-name">检索设置</div><div class="ct-sub">问答召回参数（BM25 + 可选稠密检索）</div></div></div>
        <div class="form-grid">
          <div class="form-item">
            <label>Top-K 召回条数：{{ retrForm.top_k }}</label>
            <el-slider v-model="retrForm.top_k" :min="1" :max="20" show-input :show-input-controls="false" />
          </div>
          <div class="form-item">
            <label>RRF 权重：{{ retrForm.rrf_k }}</label>
            <el-slider v-model="retrForm.rrf_k" :min="20" :max="120" :step="5" show-input :show-input-controls="false" />
          </div>
          <div class="form-item">
            <label>上下文上限（字符）：{{ retrForm.context_limit }}</label>
            <el-slider v-model="retrForm.context_limit" :min="2000" :max="16000" :step="500" show-input :show-input-controls="false" />
          </div>
          <div class="form-item">
            <label>稠密检索</label>
            <div class="switch-line">
              <el-switch v-model="retrForm.dense_enabled" />
              <span class="switch-tip">{{ retrForm.dense_enabled ? '启用 Embedding 混合检索（需 API Key）' : '仅使用 BM25 稀疏检索' }}</span>
            </div>
          </div>
        </div>
        <div class="card-foot">
          <div class="spacer"></div>
          <el-button type="primary" :loading="savingRetr" @click="saveRetrieval"><el-icon><Check /></el-icon>保存检索设置</el-button>
        </div>
      </div>

      <!-- 数据管理（危险区） -->
      <div class="card block danger">
        <div class="card-title"><div class="ct-icon red"><el-icon><WarningFilled /></el-icon></div><div><div class="ct-name">数据管理</div><div class="ct-sub">清空文档、抽取结果、对比报告与修正样本（保留 Schema 与设置）</div></div></div>
        <div class="danger-body">
          <p>此操作将删除全部业务数据且<b>不可恢复</b>。请输入 <code>DELETE</code> 确认：</p>
          <div class="danger-line">
            <el-input v-model="confirmText" placeholder="输入 DELETE" class="danger-input" />
            <el-button type="danger" :disabled="confirmText !== 'DELETE'" @click="clearData"><el-icon><Delete /></el-icon>清空全部数据</el-button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Cpu, Search, WarningFilled, CircleCheck, Close, Connection, Check, Delete } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'

const loading = ref(true)
const loadError = ref('')
const settings = ref({ model: {}, retrieval: {}, capabilities: {} })
const modelForm = ref({})
const retrForm = ref({})
const preset = ref('custom')
const savingModel = ref(false)
const savingRetr = ref(false)
const testing = ref(false)
const confirmText = ref('')

const capabilities = ref({})
const PRESETS = {
  deepseek: { base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  openai: { base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  dashscope: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  custom: {},
}
const CAP_LABELS = { llm: 'LLM 问答', ocr: 'OCR 识别', embedding: '稠密检索' }
function capLabel(key) { return CAP_LABELS[key] || key }
function hasApiKey() { return !!(settings.value.model && settings.value.model.api_key) }

function applyPreset() {
  const p = PRESETS[preset.value]
  if (!p) return
  if (p.base_url) modelForm.value.base_url = p.base_url
  if (p.model) modelForm.value.model = p.model
}
function buildModelPayload() {
  const payload = { ...modelForm.value }
  if (!payload.api_key) delete payload.api_key
  if (preset.value !== 'custom') {
    payload.base_url = modelForm.value.base_url
    payload.model = modelForm.value.model
  }
  return payload
}
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.getSettings()
    settings.value = res
    capabilities.value = res.capabilities || {}
    modelForm.value = {
      base_url: res.model.base_url || '',
      api_key: '',
      model: res.model.model || '',
      temperature: res.model.temperature ?? 0.2,
      max_tokens: res.model.max_tokens ?? 4096,
      embedding_model: res.model.embedding_model || '',
    }
    retrForm.value = {
      top_k: res.retrieval.top_k ?? 6,
      rrf_k: res.retrieval.rrf_k ?? 60,
      context_limit: res.retrieval.context_limit ?? 8000,
      dense_enabled: !!res.retrieval.dense_enabled,
    }
    const base = modelForm.value.base_url || ''
    preset.value = base.includes('deepseek') ? 'deepseek' : base.includes('openai') ? 'openai' : base.includes('dashscope') ? 'dashscope' : 'custom'
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
async function saveModel() {
  savingModel.value = true
  try {
    const res = await api.saveSettings({ model: buildModelPayload() })
    settings.value = res
    capabilities.value = res.capabilities || {}
    modelForm.value.api_key = ''
    ElMessage.success('模型设置已保存')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    savingModel.value = false
  }
}
async function testModel() {
  testing.value = true
  try {
    const res = await api.testConnection(buildModelPayload())
    if (res.ok) ElMessage.success('连接成功，模型可用 ✓')
    else ElMessage.error(res.error || '连接失败')
  } catch (e) {
    ElMessage.error(e.message || '连接失败')
  } finally {
    testing.value = false
  }
}
async function saveRetrieval() {
  savingRetr.value = true
  try {
    const res = await api.saveSettings({ retrieval: retrForm.value })
    settings.value = res
    capabilities.value = res.capabilities || {}
    ElMessage.success('检索设置已保存')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    savingRetr.value = false
  }
}
async function clearData() {
  try {
    await ElMessageBox.confirm('即将清空全部文档与业务数据，此操作不可恢复。确定继续？', '清空全部数据', { type: 'error', confirmButtonText: '确定清空' })
  } catch { return }
  try {
    await api.clearData()
    confirmText.value = ''
    ElMessage.success('数据已清空')
    await load()
  } catch (e) {
    ElMessage.error(e.message || '清空失败')
  }
}
onMounted(load)
</script>
<style scoped>
.head-row { margin-bottom: 16px; }
.cap-row { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.cap-chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 999px; font-size: 12.5px; border: 1px solid var(--dm-border); background: var(--dm-card); color: var(--dm-text-muted); }
.cap-chip.ok { color: var(--dm-success); border-color: #bfe3cc; background: #e8f7ee; }
.block { padding: 20px 24px; margin-bottom: 18px; }
.card-title { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.ct-icon { width: 42px; height: 42px; border-radius: 11px; display: flex; align-items: center; justify-content: center; }
.ct-icon.blue { background: var(--dm-primary-light); color: var(--dm-primary); }
.ct-icon.teal { background: rgba(14,116,144,.1); color: var(--dm-teal); }
.ct-icon.red { background: #fdecec; color: var(--dm-danger); }
.ct-name { font-size: 15px; font-weight: 700; color: var(--dm-text); }
.ct-sub { font-size: 12px; color: var(--dm-text-muted); margin-top: 2px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 20px; max-width: 860px; }
.form-item { display: flex; flex-direction: column; gap: 8px; }
.form-item.full { grid-column: 1 / -1; }
.form-item label { font-size: 12.5px; font-weight: 600; color: var(--dm-text); }
.switch-line { display: flex; align-items: center; gap: 10px; min-height: 32px; }
.switch-tip { font-size: 12px; color: var(--dm-text-muted); }
.card-foot { display: flex; align-items: center; margin-top: 20px; }
.spacer { flex: 1; }
.danger { border-color: #f3c1c1; background: #fffbfb; }
.danger-body p { font-size: 13px; color: var(--dm-text); margin: 0 0 12px; line-height: 1.7; }
.danger-body code { background: #fdecec; color: var(--dm-danger); font-weight: 700; padding: 1px 8px; border-radius: 5px; font-family: Consolas, monospace; }
.danger-line { display: flex; gap: 10px; max-width: 420px; }
.danger-input { flex: 1; }
</style>