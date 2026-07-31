/** 展示格式化工具。 */

export const DOC_STATUS = {
  uploaded: { label: '待解析', type: 'info' },
  parsing: { label: '解析中', type: 'warning' },
  parsed: { label: '已解析', type: 'success' },
  failed: { label: '解析失败', type: 'danger' },
}

export const TASK_STATUS = {
  pending: { label: '排队中', type: 'info' },
  running: { label: '进行中', type: 'warning' },
  succeeded: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const FIELD_STATUS = {
  extracted: { label: '已提取', type: 'success' },
  unsure: { label: '待确认', type: 'warning' },
  missing: { label: '缺失', type: 'danger' },
  invalid: { label: '无效', type: 'danger' },
}

export const DIFF_STATUS = {
  same: { label: '一致', type: 'info' },
  changed: { label: '变更', type: 'warning' },
  only_a: { label: '仅文档A', type: 'danger' },
  only_b: { label: '仅文档B', type: 'success' },
  both_missing: { label: '双方缺失', type: 'info' },
}

export const EXT_ICON = {
  '.pdf': 'Document', '.docx': 'DocumentCopy', '.xlsx': 'Grid',
  '.png': 'Picture', '.jpg': 'Picture', '.jpeg': 'Picture', '.webp': 'Picture',
}

export function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function formatTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

export function confidenceColor(score) {
  if (score == null) return 'info'
  if (score >= 0.8) return 'success'
  if (score >= 0.6) return 'warning'
  return 'danger'
}

export function statusOf(value, map) {
  return map[value] || { label: value, type: 'info' }
}
