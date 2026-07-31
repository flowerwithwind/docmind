<template>
  <div class="dropzone" :class="{ over, error: shake }" @dragover.prevent="over = true" @dragleave.prevent="over = false" @drop.prevent="onDrop">
    <el-icon :size="34" class="icon"><UploadFilled /></el-icon>
    <div class="text">{{ over ? '松开上传' : '拖拽文件到此处，或' }}</div>
    <el-button type="primary" plain size="small" @click="pick">选择文件</el-button>
    <input ref="input" type="file" class="input" :accept="accept" :multiple="multiple" @change="onPick" />
    <div v-if="files.length" class="list">
      <div v-for="(file, i) in files" :key="i" class="item">
        <span class="name">{{ file.name }}</span>
        <span class="size">{{ formatSize(file.size) }}</span>
        <el-icon class="rm" @click="remove(i)"><Close /></el-icon>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { UploadFilled, Close } from '@element-plus/icons-vue'
import { formatSize } from '@/utils/format'
const props = defineProps({ accept: { type: String, default: '.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.webp' }, multiple: { type: Boolean, default: true } })
const emit = defineEmits(['change', 'error'])
const input = ref(null)
const over = ref(false)
const shake = ref(false)
const files = ref([])
function pick() { input.value && input.value.click() }
function add(list) {
  const allowed = (props.accept || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
  const valid = [], invalid = []
  for (const file of list) {
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
    if (allowed.includes(ext)) valid.push(file); else invalid.push(file.name)
  }
  if (invalid.length) {
    shake.value = true
    setTimeout(() => { shake.value = false }, 300)
    emit('error', '不支持的文件类型：' + invalid.join('、'))
  }
  if (valid.length) {
    files.value = props.multiple ? files.value.concat(valid) : valid
    emit('change', files.value)
  }
}
function onPick(e) { add(Array.from(e.target.files || [])); e.target.value = '' }
function onDrop(e) { over.value = false; add(Array.from(e.dataTransfer.files || [])) }
function remove(i) { files.value.splice(i, 1); emit('change', files.value) }
defineExpose({ files, clear: () => { files.value = [] } })
</script>
<style scoped>
.dropzone { border: 2px dashed var(--dm-border-strong); border-radius: var(--dm-radius); padding: 28px 20px; display: flex; flex-direction: column; align-items: center; gap: 10px; background: var(--dm-fill); transition: border-color .15s ease, background .15s ease; }
.dropzone.over { border-color: var(--dm-primary); background: var(--dm-primary-light); }
.dropzone.error { border-color: var(--dm-danger); animation: dm-shake .3s; }
.icon { color: var(--dm-text-faint); }
.text { font-size: 13px; color: var(--dm-text-muted); }
.input { display: none; }
.list { width: 100%; display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
.item { display: flex; align-items: center; gap: 10px; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: 8px; padding: 7px 12px; font-size: 12.5px; }
.name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.size { color: var(--dm-text-muted); font-variant-numeric: tabular-nums; }
.rm { cursor: pointer; color: var(--dm-text-muted); } .rm:hover { color: var(--dm-danger); }
@keyframes dm-shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
</style>
