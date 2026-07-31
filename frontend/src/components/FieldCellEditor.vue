<template>
  <div class="cell" :class="{ editing }">
    <div v-if="!editing" class="view" :class="{ readonly: disabled }" @click="startEdit">
      <span v-if="display !== null && display !== ''" class="value">{{ display }}</span>
      <span v-else class="placeholder">{{ placeholder }}</span>
    </div>
    <div v-else class="edit">
      <el-input-number v-if="field.type === 'number'" v-model="draft" :controls="false" size="small" class="num" @keyup.enter="save" @blur="save" />
      <el-select v-else-if="field.enum && field.enum.length" v-model="draft" size="small" @change="save">
        <el-option v-for="opt in field.enum" :key="opt" :label="opt" :value="opt" />
      </el-select>
      <el-date-picker v-else-if="field.type === 'date'" v-model="draft" type="date" value-format="YYYY-MM-DD" size="small" @change="save" />
      <el-input v-else v-model="draft" size="small" @keyup.enter="save" @blur="save" />
    </div>
  </div>
</template>
<script setup>
import { ref, computed } from 'vue'
const props = defineProps({ field: { type: Object, required: true }, value: { type: [String, Number, Object, Array, Boolean], default: null }, disabled: { type: Boolean, default: false } })
const emit = defineEmits(['save'])
const editing = ref(false)
const draft = ref(null)
function startEdit() {
  if (props.disabled) return
  draft.value = props.value
  editing.value = true
}
function save() {
  editing.value = false
  const raw = draft.value
  if (props.field.type === 'number') {
    emit('save', raw == null || raw === '' ? null : Number(raw))
  } else if (props.field.type === 'list' && typeof raw === 'string') {
    emit('save', raw.split(/[,，]/).map((s) => s.trim()).filter(Boolean))
  } else {
    emit('save', raw)
  }
}
function displayValue(v) {
  if (v == null || v === '') return null
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
const display = computed(() => displayValue(props.value))
const placeholder = computed(() => '点击填写' + (props.field.required ? '（必填）' : ''))
</script>
<style scoped>
.cell { min-height: 32px; }
.view { padding: 5px 10px; border: 1px dashed transparent; border-radius: 8px; cursor: pointer; font-size: 13px; min-height: 30px; display: flex; align-items: center; }
.view:hover { border-color: var(--dm-primary); background: var(--dm-primary-light); }
.view.readonly { cursor: default; }
.view.readonly:hover { border-color: transparent; background: transparent; }
.value { color: var(--dm-text); word-break: break-all; }
.placeholder { color: var(--dm-text-faint); font-size: 12px; }
.edit .num { width: 160px; }
.edit :deep(.el-input__wrapper), .edit :deep(.el-select__wrapper) { border-color: var(--dm-primary); box-shadow: 0 0 0 2px var(--dm-ring-primary); }
</style>
