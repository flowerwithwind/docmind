/** 统一的 fetch 封装：JSON + 错误归一化 + 上传进度回调。 */

async function request(path, options = {}) {
  const resp = await fetch(`/api${path}`, {
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (resp.status === 204) return null
  let data = null
  const text = await resp.text()
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }
  if (!resp.ok) {
    const detail = typeof data === 'object' && data && data.detail
      ? (Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('；') : String(data.detail))
      : `请求失败（${resp.status}）`
    throw new Error(detail)
  }
  return data
}

export const http = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, file) => {
    const form = new FormData()
    form.append('file', file)
    return request(path, { method: 'POST', body: form })
  },
  postForm: (path, form) => request(path, { method: 'POST', body: form }),
  uploadMany: (path, files) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request(path, { method: 'POST', body: form })
  },
}

/** 轮询任务直到结束（带超时上限）。 */
export async function pollTask(taskId, { interval = 800, timeoutMs = 600000, onProgress } = {}) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const task = await request(`/tasks/${taskId}`)
    if (onProgress) onProgress(task)
    if (task.status === 'succeeded') return task
    if (task.status === 'failed') throw new Error(task.error || '任务失败')
    if (Date.now() > deadline) throw new Error('任务超时')
    await new Promise((r) => setTimeout(r, interval))
  }
}
