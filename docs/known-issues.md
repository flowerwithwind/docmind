# DocMind 已知问题（Known Issues）

> 记录级别：P1 = 必须修复 / P2 = 应修复 / P3 = 可优化
> 更新于：2026-07-31（v1.0.0）

## P2

### 1. 抽取任务防重非原子，并发双击可能重复调度
- **位置**：`backend/app/services/tasks.py` `schedule_extract()` → `_has_active_extract()`
- **现象**：防重采用「先查后插」，两个并发请求可同时通过检查，为同一文档 + Schema 创建两个抽取任务
- **影响**：重复抽取浪费模型调用，极端情况下结果互相覆盖
- **建议**：以 doc_id + schema_id 建唯一约束或使用 INSERT ... ON CONFLICT 原子占位；或在前端按钮加 loading 防抖

### 2. 多文件上传中途失败留下已上传文档
- **位置**：`backend/app/api/documents.py` `upload_documents()`
- **现象**：第 3 个文件类型不合法时抛 422，前 2 个文件已落库并触发解析
- **影响**：用户以为上传失败，实际部分文件已入库，造成认知偏差
- **建议**：先全量校验再入库；或失败时回滚已入库文档并清理文件（try/except + 补偿删除）

### 3. db.py 动态 UPDATE 字段名来自 f-string
- **位置**：`backend/app/storage/db.py` `update_document` / `update_extraction` / `update_task`
- **现象**：`f"UPDATE ... SET {keys}"` 由 `**fields` 的键构造
- **风险评估**：当前所有调用点均为内部白名单传参（如 status/progress/message），无外部输入直达；SQL 注入风险低
- **建议**：抽一个 `_allowed_update_fields(table, fields)` 白名单过滤函数，防御未来误用

## P3

### 4. 前端主 chunk 超过 500KB
- **位置**：`frontend/vite.config.js`（构建产物 `index-*.js` 约 1.06MB，gzip 349KB）
- **原因**：Element Plus 全量引入 + DocumentDetailView 相关组件集中
- **建议**：`manualChunks` 拆分 element-plus / vendor；或 Element Plus 按需导入（unplugin-vue-components）；体积可再降约 50%

### 5. 仓库混合 CRLF / LF 行尾
- **位置**：仓库根（git autocrlf 未统一，无 .gitattributes）
- **现象**：git 提示 `LF will be replaced by CRLF`
- **影响**：跨平台 diff 噪音，Windows / Linux 协作时行尾反复变化
- **建议**：新增 `.gitattributes` 声明 `*.py text eol=lf`、`*.vue text eol=lf`，并一次性归一化行尾

## 已关闭问题（M8 修复）

- ~~P1 API Key 明文回显~~ → 已修复（mask_api_key 脱敏 + 空值/脱敏值不覆盖）
- ~~P2 clear_data >1000 文档遗留孤儿文件~~ → 已修复（分页循环删除）
- ~~P3 main.py 版本硬编码~~ → 已修复（统一读 VERSION）
