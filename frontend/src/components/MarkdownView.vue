<template>
  <div class="markdown" v-html="html"></div>
</template>
<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import sql from 'highlight.js/lib/languages/sql'
hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('sql', sql)
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
const renderer = new marked.Renderer()
renderer.code = function (token) {
  const lang = token.lang || ''
  const text = token.text || ''
  let body
  if (lang && hljs.getLanguage(lang)) {
    try { body = hljs.highlight(text, { language: lang }).value } catch { body = escapeHtml(text) }
  } else {
    body = escapeHtml(text)
  }
  return '<pre><code class="hljs language-' + lang + '">' + body + '</code></pre>'
}
marked.use({ renderer })
const props = defineProps({ content: { type: String, default: '' } })
const html = computed(() => DOMPurify.sanitize(marked.parse(props.content || '', { async: false })))
</script>
<style scoped>
.markdown { font-size: 14px; line-height: 1.7; color: var(--dm-text); word-break: break-word; }
.markdown :deep(p) { margin: 0 0 10px; }
.markdown :deep(h1), .markdown :deep(h2), .markdown :deep(h3) { margin: 16px 0 8px; font-weight: 600; }
.markdown :deep(h1) { font-size: 18px; } .markdown :deep(h2) { font-size: 16px; } .markdown :deep(h3) { font-size: 15px; }
.markdown :deep(table) { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
.markdown :deep(th), .markdown :deep(td) { border: 1px solid var(--dm-border); padding: 6px 10px; text-align: left; }
.markdown :deep(th) { background: var(--dm-fill); font-weight: 600; }
.markdown :deep(code:not(.hljs)) { background: var(--dm-fill-strong); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
.markdown :deep(pre) { background: var(--dm-code-bg); color: var(--dm-code-text); padding: 12px 14px; border-radius: 10px; overflow-x: auto; font-size: 12.5px; }
.markdown :deep(ul), .markdown :deep(ol) { padding-left: 20px; margin: 8px 0; }
.markdown :deep(blockquote) { border-left: 3px solid var(--dm-primary); margin: 10px 0; padding: 4px 12px; color: var(--dm-text-muted); background: var(--dm-fill); }
</style>
