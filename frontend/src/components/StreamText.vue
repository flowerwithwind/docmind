<template>
  <div class="stream">
    <span>{{ shown }}</span>
    <span v-if="active" class="cursor"></span>
  </div>
</template>
<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
const props = defineProps({ text: { type: String, default: '' }, active: { type: Boolean, default: false }, speed: { type: Number, default: 16 } })
const shown = ref('')
let timer = null
let idx = 0
function stop() { if (timer) { clearTimeout(timer); timer = null } }
function tick() {
  if (!props.active || idx >= props.text.length) {
    shown.value = props.text
    stop()
    return
  }
  idx = Math.min(props.text.length, idx + 2 + Math.floor(Math.random() * 3))
  shown.value = props.text.slice(0, idx)
  timer = setTimeout(tick, props.speed)
}
watch(() => props.text, (val) => {
  if (!props.active) { shown.value = val; return }
  idx = Math.floor(shown.value.length * 0.5)
  tick()
})
watch(() => props.active, (v) => { if (v) tick(); else { shown.value = props.text; stop() } })
onBeforeUnmount(stop)
</script>
<style scoped>
.stream { white-space: pre-wrap; word-break: break-word; }
.cursor { display: inline-block; width: 2px; height: 1em; background: var(--dm-primary); vertical-align: -2px; margin-left: 2px; animation: dm-blink 1s steps(1) infinite; }
@keyframes dm-blink { 50% { opacity: 0; } }
</style>
