# DocMind M8 代码审查报告

> 审查基线：v1.0.0（commit 72a46ca 之后，M8 修复前）
> 审查方式：逐文件静态审查 + 自动化验证（pytest 106 项 / ruff / vitest 3 项 / vite build）
> 审查日期：2026-07-31

## 一、审查结论摘要

| 维度 | 结论 |
|---|---|
| 后端质量 | 良好。参数化 SQL、WAL 事务、上传白名单、SSE 断连处理、LLM 错误归一化均规范 |
| 前端质量 | 良好。XSS 防护到位（DOMPurify / 手动 escape / html.escape），无危险 innerHTML |
| 安全专项 | 发现 1 处 P1：API Key 明文回显，M8 已修复为脱敏展示 |
| 工程健康 | 发现死依赖 echarts / pinia（源码零引用），M8 已移除；主 chunk 超 500KB（见 known-issues） |
| 测试基线 | 后端 106 passed · ruff All checks passed · 前端 vitest 3/3 · build 通过 |

## 二、后端逐文件结论

### API 层（app/api/）
| 文件 | 结论 |
|---|---|
| health.py | ✅ 简洁；版本读取自 VERSION 文件，与 app.version 保持一致 |
| schemas.py | ✅ 白名单字段更新；Schema 变更校验清晰 |
| tasks.py | ✅ 任务列表/详情/取消，状态机校验完整 |
| documents.py | ✅ 上传扩展名白名单 + 数量上限；分页查询参数有边界钳制 |
| media.py | ✅ 图片访问按 doc_id 归属校验；文件路径经 resolve() 防穿越 |
| settings.py | ✅ M8 修复后 GET/PUT 均返回脱敏 API Key；test 接口不落库 |
| demo.py | ✅ 演示数据开关清晰，不影响真实数据 |
| chat.py | ✅ SSE 流式响应，客户端断连即停止生成；会话与消息事务写入 |
| extractions.py | ✅ 抽取触发前有进行中任务防重（非原子，见 known-issues） |
| compares.py | ✅ 字段级 diff 只读比对，导出走 services/export.py |
| samples.py | ✅ 样例导入幂等（按名去重） |
| data.py | ✅ M8 修复：clear_data 改为 200/页循环删除，>1000 文档不再遗留孤儿文件 |

### 服务层（app/services/）
| 文件 | 结论 |
|---|---|
| parser.py | ✅ pdfplumber/docx/openpyxl 解析异常归一化为 ParseError；页流带图片提取 |
| chunker.py | ✅ 章节感知分块 + attach_chunk_ids 幂等；块大小边界受控 |
| retrieval.py | ✅ BM25 + 稠密向量 + RRF 融合；INDEX.drop 随文档删除清理 |
| qa.py | ✅ 引用块白名单过滤，LLM 失败自动降级规则问答 |
| extraction.py | ✅ Schema 校验 + LLM 分批抽取 + 字段级置信度；失败可重试 |
| compare.py | ✅ 同 Schema 字段 diff + 章节相似度，错误类型明确 |
| export.py | ✅ HTML 导出使用 html.escape 防 XSS |
| tasks.py | ✅ 守护线程 + asyncio.to_thread 组合避免阻塞；fail_stale_tasks 处理重启残留 |
| settings.py | ✅ M8 修复：mask_api_key() 脱敏，空值/脱敏值不覆盖原 Key |

### 存储层（app/storage/）
| 文件 | 结论 |
|---|---|
| db.py | ✅ 全量参数化 SQL、WAL、外键约束；update 动态字段仅来自内部白名单调用（见 known-issues） |
| files.py | ✅ 文件名正则白名单、uuid 存储名、50MB 限流、ext 白名单；remove_* 带存在性判断 |

### 适配与工具层
| 文件 | 结论 |
|---|---|
| llm/client.py | ✅ OpenAI 兼容流式解析；M8 修复缩进；HTTPError 归一化为 LLMError；错误信息截断 300 字符 |
| fallback/extractor.py | ✅ 规则抽取器，无外部依赖可离线运行 |
| utils/limits.py | ✅ 限流中间件（按 IP + 路由） |
| utils/text.py | ✅ 文本清理/截断工具，无危险操作 |
| utils/logging.py | ✅ 结构化日志，不记录请求体 |
| models.py / config.py / seed.py | ✅ Pydantic 响应模型完整；配置集中；种子 Schema 幂等 |

### 后端负面清单（未发现项）
- ✅ 无 eval / exec / pickle / subprocess / 裸 except
- ✅ 无 SQL 字符串拼接外部输入
- ✅ 上传无路径穿越（.resolve() + uuid 存储名）
- ✅ 无 API Key 明文回显（M8 已修复）

## 三、前端逐文件结论

### 组件（src/components/，17 个）
| 组件 | 结论 |
|---|---|
| MarkdownView.vue | ✅ DOMPurify 净化后再渲染，白名单标签 |
| SourceDrawer.vue | ✅ 文件路径/文本手动 escape，无 v-html 直插 |
| StreamText.vue | ✅ 流式打字机，分段追加无重渲染风暴 |
| FileDropzone.vue | ✅ 拖拽/选择双入口，类型与大小前置校验 |
| ChunkBlock.vue / StructureTree.vue | ✅ 结构树递归组件，无深度爆栈风险 |
| CompareTable.vue / ConfidenceBar.vue / FieldCellEditor.vue | ✅ diff 展示与行内编辑，输入受控 |
| DocIcon / EmptyState / ErrorState / SampleCard / SkeletonLoader / StatCard / StatusBadge / TaskProgress | ✅ 纯展示组件，props 类型明确 |

### 视图（src/views/，10 个）
| 视图 | 结论 |
|---|---|
| HomeView.vue | ✅ 工作台统计 + 快捷入口；页脚版本号随 VERSION 同步 |
| DocumentsView.vue | ✅ 列表分页 + 筛选 + 批量上传 + 删除确认 |
| DocumentDetailView.vue | ✅ 预览/问答/抽取/对比四 Tab 组合，任务进度统一 |
| detail/PreviewTab.vue | ✅ 页流渲染，图片懒加载 |
| detail/QaTab.vue | ✅ SSE 流式问答 + 引用跳转 |
| detail/ExtractTab.vue | ✅ 抽取结果可视化编辑 + 快照确认 |
| detail/CompareTab.vue | ✅ 多文档对比 + 导出 |
| SchemasView.vue / SamplesView.vue / SettingsView.vue | ✅ CRUD 规范；设置页展示脱敏 API Key |

### 逻辑层
| 文件 | 结论 |
|---|---|
| api/（http.js / index.js / chat.js） | ✅ fetch 封装统一错误处理；SSE 用 fetch reader 解析 |
| composables/useTask.js | ✅ 轮询 + 取消，组件卸载清理定时器 |
| composables/useTheme.js | ✅ 主题持久化，无闪烁 |
| router/index.js | ✅ 懒加载路由 + 404 兜底 |
| utils/format.js | ✅ 纯函数格式化，单测覆盖 3/3 |

### 前端负面清单
- ✅ 无危险 innerHTML（已净化组件除外）
- ✅ 无 eval / Function 动态执行
- ✅ 死依赖 echarts / pinia 已移除（main.js 同步清理 createPinia）

## 四、M8 已修复问题

| # | 级别 | 问题 | 修复 |
|---|---|---|---|
| 1 | P1 | GET/PUT /api/settings 明文返回 API Key | services/settings.py 新增 mask_api_key()（前4后4）；api/settings.py 统一脱敏；空值/脱敏值视为未修改，原 Key 保留 |
| 2 | P2 | clear_data 单次拉取 1000 条，>1000 文档遗留孤儿文件 | api/data.py 改为 200/页循环删除直至 total 耗尽 |
| 3 | P2 | main.py version 硬编码 0.1.0，与 VERSION 文件漂移 | 新增 _read_version()，FastAPI version 与健康检查统一读 VERSION |
| 4 | P3 | llm/client.py chat_stream 过深缩进（8 格） | 修正为 4 格，通过 ruff 校验 |
| 5 | P3 | 前端死依赖 echarts / pinia（零引用） | package.json 删除依赖；main.js 移除 createPinia；README 技术栈同步更新 |
| 6 | P3 | 前端页脚版本号硬编码 v0.1.0 | App.vue / HomeView.vue 同步为 v1.0.0 |

## 五、回归验证结果

| 验证项 | 结果 |
|---|---|
| pytest（后端全量） | 106 passed（含新增 API Key 脱敏用例） |
| ruff check app | All checks passed |
| vitest run（前端） | 3/3 passed |
| npm run build | 构建成功（主 chunk 警告见 known-issues） |
| VERSION / app.version | 均读取为 1.0.0 |

## 六、B1~B5 阶段复盘（v1.1.0）

> 复盘范围：B1 基线 → B5 P3 精选（2026-07-31 ~ 2026-08-01），对照 docs/需求开发文档.md §9 里程碑与 known-issues 的演变。

| 阶段 | 关键提交 | 架构决策 | 风险 | 教训 |
|---|---|---|---|---|
| B1 基线 | 590e12c ~ 542b3a5（M1~M8）、209fc39（S0 环境基线） | 以 M1~M8 既有实现为基线固化：FastAPI 分层（api/services/storage）、SQLite WAL + 外键、Vue3 懒加载路由；版本统一读取 VERSION 文件 | 基线测试集中于 API 集成层，服务层边界用例偏少 | 回归先行：任何里程碑改动前先跑全量 pytest / ruff / vitest / build，锁定基线再动手 |
| B2 表格问答后端 | 37c2acd | Excel/PDF 表格转可查询数据（table_store 存储层）+ NL2SQL 链路 + SQL 白名单校验（validate_sql / ensure_limit），无 Key 降级规则问答 | 自然语言 → SQL 引入新的注入面 | SQL 仅允许 SELECT + 表/列白名单 + 行数上限钳制；LLM 输出全部 mock 化，测试 hermetic，不依赖网络/Key |
| B3 表格问答前端 | 74b56fc | 详情页新增「表格问答」Tab：文档表格选择 + NL2SQL 结果面板 + ECharts 图表/降级标识/错误态 | 主 chunk 进一步膨胀 | 功能按 Tab 懒加载隔离；体积问题如实记入 known-issues（P3），交由 B5 统一处理 |
| B4 P2 修复 | dc0650e / 82a74e2 / 109ee9d | 抽取防重原子化（doc_id + schema_id 唯一约束 + ON CONFLICT 原子占位）；多文件上传先全量校验再入库 + 失败补偿删除；db.py 动态 UPDATE 白名单过滤；前端抽取按钮 loading 防抖 | 并发双击重复建任务；上传第 N 个失败残留部分文件；f-string 拼接 SQL 字段名 | 先写失败用例再修（并发线程、残留断言、未知字段拒绝），修复后新增 11 项测试（pytest 161）；前端防抖与后端原子占位双保险 |
| B5 P3 精选 | 4ce1354 | vite manualChunks 将 element-plus / echarts 等拆为独立 vendor chunk；新增 .gitattributes（源码 eol=lf）+ git add --renormalize 一次性归一化行尾 | index 349KB / DocumentDetailView 437KB（gzip）主 chunk 过大；仓库 CRLF/LF 混合 | 以构建产物 gzip 实测验收（主 chunk 降至 3.3KB / 18.1KB）；行尾归一化仅限 .gitattributes 覆盖的源码模式，diff 无噪音 |

### 复盘要点

- **架构决策**：SQLite + 文件目录双存储、SSE 流式问答、无 Key 降级规则引擎、人机校验闭环是项目四大核心决策；B1~B5 均在不推翻既有架构的前提下增量演进（新增 table_store 存储层，复用 db 层加唯一约束与白名单过滤）。
- **主要风险**：① SQL 注入面扩大（NL2SQL 新链路）→ 白名单 + 行数钳制闭环；② 并发与部分失败一致性（任务防重、批量上传）→ 原子占位 + 补偿删除；③ 前端体积与工程卫生 → manualChunks 分包 + 行尾规范。
- **教训**：① 防重必须落在数据库约束层，业务层「先查后插」不可靠；② 批量操作要么全成要么全败，补偿逻辑要可测试（断言文档/任务/文件零残留）；③ 动态 SQL 字段一律白名单过滤，防御未来误用；④ 性能优化以构建产物实测为准，不凭直觉；⑤ 行尾归一化必须用 .gitattributes 声明范围，避免大规模无关 diff。
