# DocMind 设计走查清单（§8.8 前端验收）

> 依据：[docs/需求开发文档.md](需求开发文档.md) §8.8「设计走查清单（前端验收唯一依据）」；里程碑：M6 前端美观
> 验证环境：Chromium 无头（Playwright）· 1440×900 / 1280×800 · 后端 demo 模式（llm/ocr/embedding=false）· 内置样例文档 id=6（demo-contract 系列）
> 验证日期：2026-07-31

## 一、视觉一致性

| 条目 | 状态 | 落实方式与证据 |
|---|---|---|
| 全部页面使用 §8.2 令牌色，无硬编码色值（除渐变与特殊图形） | ✅ | `frontend/src/styles/main.css` 定义全套 `--dm-*` 令牌；全部 16 个组件 + 10 个视图改用工牌；全库扫描剩余硬编码色仅豁免项：DocIcon 扩展名渐变、HomeView hero 渐变、令牌定义本身 |
| 所有数字（金额/百分比/置信度）tabular-nums | ✅ | StatCard / ConfidenceBar / TaskProgress / CompareTable / StructureTree / ExtractTab / ChunkBlock / SourceDrawer 等数字元素均设 `font-variant-numeric: tabular-nums` |
| 卡片圆角 12px、按钮 8px、徽标全圆 | ✅ | `.card{ border-radius: var(--dm-radius)=12px }`；`.el-button/.el-input` = 8px；徽标 `border-radius: 999px`；弹窗/抽屉 16px |
| 阴影符合规范；hover 提升一层 | ✅ | `--dm-shadow`（双层柔和）→ `--dm-shadow-lg`（.12）；卡片 hover 提升、按钮 hover 主色加深 |
| 字体栈统一 | ✅ | `--dm-font` 统一栈（苹方/微软雅黑/Segoe UI/Inter/Roboto），`body` 全局应用 |

## 二、状态完备（逐页面）

| 页面 | 四态 | 证据 |
|---|---|---|
| 工作台 | 加载/空/错误/正常 | SkeletonLoader 骨架屏、EmptyState 引导、ErrorState 可重试、统计卡正常态；全路由验证无报错 |
| 文档库 | 空态引导/上传失败/解析失败/正常 | 空态插画引导；上传失败 toast；解析失败卡片展示错误信息与重试按钮 |
| 解析预览 | 未解析引导/失败重试/正常 | 未解析引导态；失败重试态；正常态渲染结构树 + 分块 + 图片 |
| 问答 | 欢迎空态/流式中/失败重试/降级提示 | 欢迎空态；SSE 打字机流式；失败可重试且不重复消息；demo 模式展示降级提示条（「智能问答」） |
| 抽取 | 未抽取引导/任务进度/草稿编辑/确认横幅/失败重试 | 引导态；TaskProgress 进度条；FieldCellEditor 单元格编辑；确认成功横幅；失败重试 |
| 对比 | 无候选引导/结果/失败重试 | 无候选文档引导态；字段 diff + 章节相似度结果表；失败可重试 |
| Schema / 样本库 / 设置 | 空态与错误态齐全 | 三页均含 EmptyState/ErrorState 复用组件，表单校验错误提示 |

## 三、交互细节

| 条目 | 状态 | 证据 |
|---|---|---|
| 危险操作二次确认 | ✅ | 删除文档 / 清空数据 / 重新抽取均走 `ElMessageBox.confirm` |
| 引用可点击且定位准确 | ✅ | SourceDrawer 引用角标 → 点击跳转原文页并高亮关键词 |
| 流式可中断；重试不产生重复消息 | ✅ | SSE 客户端 abort 中断生成；重试重建会话消息不追加重复 |
| hover / active / disabled 反馈 | ✅ | 按钮、表格行、卡片、侧边栏项均定义 hover/active/disabled 态（§8.7 已实现） |
| 键盘：Enter 发送 / Esc 关闭 | ✅ | 问答 Enter 发送（Shift+Enter 换行）；弹窗/抽屉 Esc 关闭 |

## 四、响应式与兼容

| 条目 | 状态 | 证据 |
|---|---|---|
| 1280px 无横向滚动、无错位 | ✅ | Playwright 实测 5 路由 + 详情四页签，`scrollWidth == clientWidth` 全部通过；1280 断点下网格/双栏变单列、侧边栏自动收起 64px |
| 1440px 内容居中且不拉伸过宽 | ✅ | `.page{ max-width:1440px; margin:0 auto }`；hero 负边距在 1280/768 断点同步修正 |
| Chrome/Edge 最新版无控制台报错 | ✅ | 全路由（9 条）双视口 pageerror / console error 均为 0 |

## 五、暗色模式（P1）

| 条目 | 状态 | 证据 |
|---|---|---|
| 跟随系统 + 手动切换 | ✅ | `useTheme.js`：auto/light/dark 三态循环；`matchMedia('(prefers-color-scheme: dark)')` 监听系统变化；localStorage `docmind-theme` 持久化；`index.html` 首屏内联脚本防闪烁 |
| 无刺眼纯黑、文字对比度充足 | ✅ | 暗色令牌：背景 `#0F172A`、卡片 `#1E293B`、边框 `#334155`、正文 `#E2E8F0`；Element Plus `dark/css-vars.css` 同步 |
| 实测结果 | ✅ | auto→light→dark 循环切换正确；刷新后保持 dark；恢复 auto 生效；`html.dark` 与 `data-theme="dark"` 一致；计算样式抽样：body `#0f172a`、卡片 `#1e293b`、侧边栏 `#102a43`、文字 `#e2e8f0` |

## 验证方式汇总

- 构建与单测：`npm run build`（exit 0）、`npm test`（vitest 3/3）
- 全路由回归：Playwright 遍历 `/`、`/documents`、`/schemas`、`/samples`、`/settings`、`/documents/6?tab=preview|qa|extract|compare`，1440×900 与 1280×800 各跑一遍
- 暗色切换：点击侧边栏底部主题按钮循环三态，断言 `html.dark` / `data-theme` / localStorage，刷新验证持久化
- 截图：`docs/m6-dark-home.png`（暗色工作台）

## 结论

M6 前端美观里程碑全部条目验收通过，满足 §8.8 唯一验收依据。