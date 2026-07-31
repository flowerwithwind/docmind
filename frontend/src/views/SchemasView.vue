<template>
  <div class="page">
    <div class="head-row">
      <div><h1 class="page-title">抽取 Schema</h1><p class="page-sub">定义结构化抽取的字段，内置 Schema 可直接使用，自定义 Schema 支持编辑与 JSON 双模式</p></div>
      <el-button type="primary" size="large" @click="openCreate"><el-icon><Plus /></el-icon>新建 Schema</el-button>
    </div>

    <!-- 加载/错误 -->
    <div v-if="loadError" class="card"><ErrorState :message="loadError" @retry="load" /></div>
    <div v-else-if="loading" class="card"><SkeletonLoader variant="table" :rows="6" /></div>

    <template v-else>
      <!-- 内置 Schema -->
      <div v-if="builtins.length" class="block">
        <div class="block-title">内置 Schema <span class="block-sub">只读 · 覆盖合同与财报常见场景</span></div>
        <div class="builtin-grid">
          <div v-for="s in builtins" :key="s.id" class="builtin-card">
            <div class="bc-head">
              <div class="bc-icon"><el-icon :size="20"><component :is="schemaIcon(s)" /></el-icon></div>
              <div class="bc-info">
                <div class="bc-name">{{ s.name }}</div>
                <div class="bc-key">{{ s.key }}</div>
              </div>
              <el-tag size="small" effect="plain">内置</el-tag>
            </div>
            <div class="bc-desc">{{ s.description || '暂无描述' }}</div>
            <div class="bc-foot">
              <span class="bc-count">{{ s.fields.length }} 个字段</span>
              <el-button link type="primary" size="small" @click="showPreview(s)">查看字段</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 自定义 Schema -->
      <div class="block">
        <div class="block-title">自定义 Schema <span class="block-sub">可编辑、可删除</span></div>
        <div v-if="customs.length" class="card table-card">
          <el-table :data="customs">
            <el-table-column label="名称" min-width="160">
              <template #default="{ row }">
                <div class="c-name">{{ row.name }}</div>
                <div class="c-key">{{ row.key }}</div>
              </template>
            </el-table-column>
            <el-table-column label="描述" prop="description" min-width="220" show-overflow-tooltip>
              <template #default="{ row }"><span :class="{ muted: !row.description }">{{ row.description || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="字段数" width="100">
              <template #default="{ row }"><span class="mono">{{ row.fields.length }}</span></template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }"><span class="mono">{{ formatTime(row.created_at) }}</span></template>
            </el-table-column>
            <el-table-column label="操作" width="160" align="right">
              <template #default="{ row }">
                <div class="row-ops">
                  <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                  <el-button link type="danger" @click="removeSchema(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else class="card"><EmptyState icon="Grid" title="还没有自定义 Schema" desc="基于内置 Schema 新建副本，或从零定义自己的抽取字段">
          <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>新建 Schema</el-button>
        </EmptyState></div>
      </div>
    </template>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑 Schema' : '新建 Schema'" width="760px" :close-on-click-modal="false" top="6vh">
      <el-tabs v-model="editMode">
        <el-tab-pane label="表单模式" name="form">
          <div v-if="formError" class="form-error"><el-icon><WarningFilled /></el-icon><span>{{ formError }}</span></div>
          <div class="form-grid">
            <div class="form-item">
              <label>Key <span class="req">*</span></label>
              <el-input v-model="form.key" placeholder="小写字母开头，如 contract_v2" :disabled="editing" />
              <div class="hint">小写字母开头，仅允许字母、数字、下划线</div>
            </div>
            <div class="form-item">
              <label>名称 <span class="req">*</span></label>
              <el-input v-model="form.name" placeholder="如：房屋租赁合同" />
            </div>
            <div class="form-item full">
              <label>描述</label>
              <el-input v-model="form.description" placeholder="该 Schema 用于抽取哪些信息（可选）" />
            </div>
          </div>

          <div class="fields-head">
            <span>字段定义 <span class="req">*</span></span>
            <el-button size="small" type="primary" plain @click="addField"><el-icon><Plus /></el-icon>添加字段</el-button>
          </div>
          <div v-if="!form.fields.length" class="fields-empty">至少添加一个字段</div>
          <div v-for="(f, i) in form.fields" :key="i" class="field-row">
            <el-input v-model="f.key" placeholder="key" class="f-key" :class="{ invalid: f.invalidKey }" />
            <el-input v-model="f.label" placeholder="名称" class="f-label" />
            <el-select v-model="f.type" class="f-type">
              <el-option v-for="(label, t) in TYPE_LABELS" :key="t" :label="label" :value="t" />
            </el-select>
            <el-tooltip content="必填" placement="top"><el-switch v-model="f.required" class="f-req" /></el-tooltip>
            <el-input v-model="f.enumText" placeholder="枚举值，逗号分隔（可选）" class="f-enum" />
            <el-input v-model="f.description" placeholder="说明（可选）" class="f-desc" />
            <el-button circle size="small" type="danger" plain @click="form.fields.splice(i, 1)"><el-icon><Delete /></el-icon></el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="JSON 模式" name="json">
          <div v-if="jsonError" class="form-error"><el-icon><WarningFilled /></el-icon><span>{{ jsonError }}</span></div>
          <el-input v-model="jsonText" type="textarea" :rows="16" class="json-area" placeholder='{ "key": "contract_v2", "name": "…", "fields": [ … ] }' />
          <div class="hint">支持 key / name / description / fields（key、label、type、required、enum、description）。切换回表单模式会自动解析 JSON。</div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存 Schema</el-button>
      </template>
    </el-dialog>

    <!-- 内置字段预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewSchema?.name" width="640px">
      <el-table :data="previewSchema?.fields || []">
        <el-table-column label="Key" prop="key" min-width="140"><template #default="{ row }"><span class="mono">{{ row.key }}</span></template></el-table-column>
        <el-table-column label="名称" prop="label" min-width="120" />
        <el-table-column label="类型" width="90"><template #default="{ row }"><el-tag size="small" effect="plain">{{ TYPE_LABELS[row.type] || row.type }}</el-tag></template></el-table-column>
        <el-table-column label="必填" width="70"><template #default="{ row }"><span v-if="row.required" class="req">必填</span><span v-else class="muted">—</span></template></el-table-column>
        <el-table-column label="约束/说明" min-width="160"><template #default="{ row }">{{ row.enum && row.enum.length ? row.enum.join(' / ') : (row.description || '—') }}</template></el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, WarningFilled, Document, Files, Tickets } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import { formatTime } from '@/utils/format'

const TYPE_LABELS = { string: '文本', number: '数值', date: '日期', list: '列表', object: '对象' }
const KEY_RE = /^[a-z][a-z0-9_]*$/
const schemas = ref([])
const loading = ref(true)
const loadError = ref('')
const dialogVisible = ref(false)
const previewVisible = ref(false)
const previewSchema = ref(null)
const editing = ref(null)
const editMode = ref('form')
const saving = ref(false)
const formError = ref('')
const jsonError = ref('')
const form = ref({ key: '', name: '', description: '', fields: [] })
const jsonText = ref('')

const builtins = computed(() => schemas.value.filter((s) => s.is_builtin))
const customs = computed(() => schemas.value.filter((s) => !s.is_builtin))

function schemaIcon(s) {
  return s.key.startsWith('contract') ? Files : s.key.startsWith('financial') ? Tickets : Document
}
function fieldToRow(f) {
  return { key: f.key, label: f.label, type: f.type || 'string', required: !!f.required, enumText: (f.enum || []).join(', '), description: f.description || '', invalidKey: false }
}
function rowToField(r) {
  const f = { key: r.key.trim(), label: r.label.trim(), type: r.type, required: r.required, description: r.description.trim() }
  const enumList = r.enumText.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  if (enumList.length) f.enum = enumList
  return f
}
function openCreate() {
  editing.value = null
  editMode.value = 'form'
  formError.value = ''
  jsonError.value = ''
  form.value = { key: '', name: '', description: '', fields: [fieldToRow({ key: '', label: '', type: 'string', required: false, description: '' })] }
  jsonText.value = ''
  dialogVisible.value = true
}
function openEdit(s) {
  editing.value = s
  editMode.value = 'form'
  formError.value = ''
  jsonError.value = ''
  form.value = { key: s.key, name: s.name, description: s.description || '', fields: s.fields.map(fieldToRow) }
  jsonText.value = JSON.stringify({ key: s.key, name: s.name, description: s.description || '', fields: s.fields }, null, 2)
  dialogVisible.value = true
}
function showPreview(s) {
  previewSchema.value = s
  previewVisible.value = true
}
function addField() {
  form.value.fields.push(fieldToRow({ key: '', label: '', type: 'string', required: false, description: '' }))
}
function validateForm() {
  formError.value = ''
  if (!KEY_RE.test(form.value.key)) return 'Key 必须以小写字母开头，仅含小写字母、数字、下划线'
  if (!form.value.name.trim()) return '请填写 Schema 名称'
  if (!form.value.fields.length) return '至少需要一个字段'
  const seen = new Set()
  for (const f of form.value.fields) {
    f.invalidKey = false
    if (!KEY_RE.test(f.key.trim())) {
      f.invalidKey = true
      return '字段 Key「' + (f.key || '(空)') + '」格式不正确（小写字母开头，仅字母数字下划线）'
    }
    if (seen.has(f.key.trim())) return '字段 Key 重复：' + f.key
    seen.add(f.key.trim())
    if (!f.label.trim()) return '字段「' + f.key + '」缺少名称'
  }
  return ''
}
function parseJson() {
  jsonError.value = ''
  let obj
  try {
    obj = JSON.parse(jsonText.value)
  } catch (e) {
    jsonError.value = 'JSON 解析失败：' + e.message
    return null
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) { jsonError.value = 'JSON 顶层必须是对象（含 key/name/fields）'; return null }
  if (!Array.isArray(obj.fields) || !obj.fields.length) { jsonError.value = 'fields 必须是至少包含一个字段的数组'; return null }
  return obj
}
async function save() {
  let payload
  if (editMode.value === 'json') {
    const obj = parseJson()
    if (!obj) return
    payload = { key: obj.key ?? form.value.key, name: obj.name ?? '', description: obj.description ?? '', fields: obj.fields }
    if (!KEY_RE.test(payload.key)) { jsonError.value = 'Key 必须以小写字母开头，仅含小写字母、数字、下划线'; return }
    if (!payload.name) { jsonError.value = '请填写 Schema 名称'; return }
    if (editing.value && payload.key !== editing.value.key) { jsonError.value = '编辑时不可修改 Key'; return }
  } else {
    const err = validateForm()
    if (err) { formError.value = err; return }
    payload = {
      key: form.value.key.trim(),
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      fields: form.value.fields.map(rowToField),
    }
  }
  saving.value = true
  try {
    if (editing.value) await api.updateSchema(editing.value.id, payload)
    else await api.createSchema(payload)
    ElMessage.success(editing.value ? 'Schema 已更新' : 'Schema 已创建')
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
async function removeSchema(s) {
  try {
    await ElMessageBox.confirm('删除自定义 Schema「' + s.name + '」？已有抽取结果的 Schema 不可删除。', '删除 Schema', { type: 'warning', confirmButtonText: '删除' })
  } catch { return }
  try {
    await api.deleteSchema(s.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    schemas.value = await api.listSchemas()
  } catch (e) {
    loadError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<style scoped>
.head-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.block { margin-bottom: 28px; }
.block-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 700; color: var(--dm-navy); margin-bottom: 12px; }
.block-sub { font-size: 12px; font-weight: 400; color: var(--dm-text-muted); }
.builtin-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.builtin-card { background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); box-shadow: var(--dm-shadow); padding: 16px 18px; transition: box-shadow .15s, transform .15s; }
.builtin-card:hover { box-shadow: var(--dm-shadow-lg); transform: translateY(-2px); }
.bc-head { display: flex; align-items: center; gap: 12px; }
.bc-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--dm-primary-light); color: var(--dm-primary); display: flex; align-items: center; justify-content: center; }
.bc-info { flex: 1; min-width: 0; }
.bc-name { font-size: 14.5px; font-weight: 700; color: var(--dm-text); }
.bc-key { font-size: 11px; color: #9fb3c8; font-variant-numeric: tabular-nums; }
.bc-desc { font-size: 12.5px; color: var(--dm-text-muted); line-height: 1.6; margin: 12px 0; min-height: 38px; }
.bc-foot { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid #f1f5f9; padding-top: 10px; }
.bc-count { font-size: 12px; color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.table-card { padding: 8px 12px 12px; }
.c-name { font-size: 13.5px; font-weight: 600; color: var(--dm-text); }
.c-key { font-size: 11px; color: #9fb3c8; font-variant-numeric: tabular-nums; }
.row-ops { display: flex; justify-content: flex-end; }
.mono { font-variant-numeric: tabular-nums; }
.muted { color: #b6c2d2; }
.req { color: var(--dm-danger); }
.form-error { display: flex; align-items: center; gap: 8px; background: #fdecec; border: 1px solid #f3c1c1; color: var(--dm-danger); font-size: 12.5px; padding: 9px 12px; border-radius: 8px; margin-bottom: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; margin-bottom: 16px; }
.form-item { display: flex; flex-direction: column; gap: 6px; }
.form-item.full { grid-column: 1 / -1; }
.form-item label { font-size: 12.5px; font-weight: 600; color: var(--dm-text); }
.hint { font-size: 11px; color: var(--dm-text-muted); line-height: 1.5; }
.fields-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 600; color: var(--dm-text); margin: 4px 0 10px; }
.fields-empty { padding: 24px; text-align: center; color: #b6c2d2; font-size: 12.5px; border: 1px dashed var(--dm-border); border-radius: 10px; }
.field-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.field-row :deep(.el-input__wrapper), .field-row :deep(.el-select__wrapper) { border-radius: 8px; }
.f-key { width: 130px; }
.f-label { width: 120px; }
.f-type { width: 100px; }
.f-req { margin: 0 6px; }
.f-enum { flex: 1; min-width: 120px; }
.f-desc { flex: 1.2; min-width: 140px; }
.field-row :deep(.el-input.invalid .el-input__wrapper) { box-shadow: 0 0 0 1px var(--dm-danger) inset; }
.json-area :deep(textarea) { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; line-height: 1.6; }
</style>