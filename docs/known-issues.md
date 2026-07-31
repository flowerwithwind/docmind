# DocMind 已知问题（Known Issues）

> 记录级别：P1 = 必须修复 / P2 = 应修复 / P3 = 可优化
> 更新于：2026-08-01（v1.1.0）

## P3

### 1. Element Plus 全量引入，vendor chunk 偏大
- **位置**：`frontend/src/main.js`（全量 `app.use(ElementPlus)`）
- **现象**：B5 分包后 `vendor-element-plus-*.js` 原始 816KB / gzip 258KB
- **影响**：首屏仍需下载约 258KB（gzip），弱网环境首屏偏慢
- **建议**：按需导入（unplugin-vue-components）或仅注册用到的组件，体积可再降约 50%

### 2. ECharts 全量引入，vendor chunk 偏大
- **位置**：`frontend/src/views/detail/TableQaTab.vue`（`echarts` 全量 import）
- **现象**：`vendor-echarts-*.js` 原始 1.1MB / gzip 378KB
- **影响**：仅表格问答使用图表，却全量加载 ECharts
- **建议**：按需注册（echarts/core + 用到的图表/组件）或延迟加载，可降至 200KB 以内

### 3. SQLite 单机部署上限
- **位置**：`backend/app/storage/db.py`（SQLite + 文件目录存储）
- **现象**：单写者模型 + 文件存储，适合单实例部署
- **影响**：多实例水平扩展 / 高并发写入受限
- **建议**：如需多实例部署，迁移 PostgreSQL（SQL 已参数化，改造成本集中在连接层）

### 4. FastAPI TestClient 依赖弃用告警
- **位置**：`backend/tests/`（`fastapi.testclient`）
- **现象**：pytest 输出 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`
- **影响**：仅为测试期告警，不影响功能
- **建议**：后续升级依赖时按提示安装 httpx2 消除告警

## 已关闭问题（B4/B5 修复）

- ~~P2 抽取任务防重非原子，并发双击可能重复调度~~ → 已修复（doc_id + schema_id 唯一约束 + INSERT ... ON CONFLICT 原子占位；前端「抽取/重新抽取」按钮 loading 防抖）
- ~~P2 多文件上传中途失败留下已上传文档~~ → 已修复（先全量校验（格式/大小）再入库，任一文件失败整体失败并补偿删除已入库文档/任务/文件）
- ~~P2 db.py 动态 UPDATE 字段名来自 f-string~~ → 已修复（新增白名单过滤函数，拒绝未知字段）
- ~~P3 前端主 chunk 超过 500KB~~ → 已修复（manualChunks 拆 element-plus/echarts 等 vendor：index gzip 349KB → 3.3KB、DocumentDetailView 437KB → 18.1KB）
- ~~P3 仓库混合 CRLF / LF 行尾~~ → 已修复（.gitattributes 声明源码 eol=lf + git add --renormalize 归一化）

## 已关闭问题（M8 修复）

- ~~P1 API Key 明文回显~~ → 已修复（mask_api_key 脱敏 + 空值/脱敏值不覆盖）
- ~~P2 clear_data >1000 文档遗留孤儿文件~~ → 已修复（分页循环删除）
- ~~P3 main.py 版本硬编码~~ → 已修复（统一读 VERSION）
