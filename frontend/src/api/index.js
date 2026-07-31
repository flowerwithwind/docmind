/** 统一 API 封装：所有后端接口的 JS 入口。 */
import { http, pollTask } from '@/api/http'

function qs(params) {
  const url = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== '' && v != null) url.append(k, v)
  }
  const s = url.toString()
  return s ? '?' + s : ''
}

export const api = {
  // 文档
  listDocuments: (params) => http.get('/documents' + qs(params)),
  getDocument: (id) => http.get('/documents/' + id),
  uploadDocuments: (files) => http.uploadMany('/documents/upload', files),
  reparseDocument: (id) => http.post('/documents/' + id + '/reparse'),
  deleteDocument: (id) => http.delete('/documents/' + id),
  // 任务
  getTask: (id) => http.get('/tasks/' + id),
  pollTask,
  // Schema
  listSchemas: () => http.get('/schemas'),
  createSchema: (body) => http.post('/schemas', body),
  updateSchema: (id, body) => http.put('/schemas/' + id, body),
  deleteSchema: (id) => http.delete('/schemas/' + id),
  // 抽取
  listExtractions: (docId) => http.get('/documents/' + docId + '/extractions'),
  getExtraction: (id) => http.get('/extractions/' + id),
  startExtract: (docId, schemaId) => http.post('/documents/' + docId + '/extract', { schema_id: schemaId }),
  editExtraction: (id, data) => http.put('/extractions/' + id, { data }),
  confirmExtraction: (id) => http.post('/extractions/' + id + '/confirm'),
  reextract: (id) => http.post('/extractions/' + id + '/reextract'),
  exportExtraction: (id, format) => '/api/extractions/' + id + '/export?format=' + format,
  // 修正样本
  listSamples: (params) => http.get('/samples' + qs(params)),
  exportSamples: (params) => '/api/samples/export' + qs(params),
  deleteSample: (id) => http.delete('/samples/' + id),
  clearSamples: () => http.delete('/samples'),
  // 设置
  getSettings: () => http.get('/settings'),
  saveSettings: (body) => http.put('/settings', body),
  testConnection: (model) => http.post('/settings/test', { model }),
  clearData: () => http.delete('/data?confirm=DELETE'),
  // 演示
  demoInfo: () => http.get('/demo'),
  demoLoad: (kind) => http.post('/demo/load/' + kind),
  // 对比
  startCompare: (body) => http.post('/compare', body),
  listCompares: (docId) => http.get('/compares' + (docId ? '?doc_id=' + docId : '')),
  getCompare: (id) => http.get('/compares/' + id),
  exportCompare: (id, fmt) => '/api/compares/' + id + '/export?fmt=' + fmt,
  // 会话与问答
  listSessions: () => http.get('/sessions'),
  createSession: (body) => http.post('/sessions', body),
  getSession: (id) => http.get('/sessions/' + id),
  deleteSession: (id) => http.delete('/sessions/' + id),
  chat: (docId, body) => http.post('/documents/' + docId + '/chat', body),
  // 表格问答
  listQaTables: () => http.get('/qa/tables'),
  tableQa: (body) => http.post('/qa/table', body),
}
