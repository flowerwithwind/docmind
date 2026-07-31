/** 流式问答：fetch + ReadableStream 解析 SSE（meta/delta/done/error）。
 * 支持 AbortController 中断；done 后由调用方刷新会话消息以获取引用。
 */
export async function streamChat(docId, body, handlers, signal) {
  const resp = await fetch('/api/documents/' + docId + '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok || !resp.body) {
    let detail = '请求失败（' + resp.status + '）'
    try {
      const data = await resp.json()
      if (data && data.detail) detail = data.detail
    } catch { /* 非 JSON 响应 */ }
    throw new Error(detail)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let sessionId = null
  let messageId = null
  let doneFlag = false
  const emit = (fn, payload) => { if (typeof fn === 'function') fn(payload) }
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        let event = 'message'
        const dataLines = []
        for (const line of raw.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (!dataLines.length) continue
        let payload = {}
        try { payload = JSON.parse(dataLines.join('\n')) } catch { continue }
        if (event === 'meta') {
          sessionId = payload.session_id != null ? payload.session_id : sessionId
          messageId = payload.message_id != null ? payload.message_id : messageId
        } else if (event === 'delta') {
          emit(handlers.onDelta, payload.text || '')
        } else if (event === 'done') {
          doneFlag = true
          emit(handlers.onDone, payload)
        } else if (event === 'error') {
          emit(handlers.onError, payload.message || '生成失败')
          doneFlag = true
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
  return { sessionId, messageId, done: doneFlag }
}
