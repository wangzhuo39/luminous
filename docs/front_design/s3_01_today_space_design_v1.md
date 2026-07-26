# Luminous S3 Design 01：Today 晨光窗与时间信息架构

> 状态：实现基线 v1
> 设计：Gemini；工程边界与完整性审查：Codex
> 初稿 trace：`/home/wz/gemini-api-traces/runs/20260725T020200.934833Z_luminous-s3-design01-today-space_4350587a/`
> 修订 trace：`/home/wz/gemini-api-traces/runs/20260725T020537.485094Z_luminous-s3-design01-today-space-repair_da848736/`
> 补充 trace：`/home/wz/gemini-api-traces/runs/20260725T020658.313718Z_luminous-s3-design01-today-supplement_8b328d3d/`

## 1. 体验哲学与视觉意图

Today 是温室中的“晨光透窗”，不是任务收割机。它温和地折射今天的形状，保持半透明和留白，让主场景与陪伴者在背景中可感知。

- 禁止红色警报、KPI、进度条、统计面板、红点和催促文案。
- 任务是待照看的生活锚点，不是逾期债务。
- 状态和排序必须确定，不使用随机文案或虚构同步时间。
- 不展示接口不提供的天气、心情或建议。

## 2. 空间布局

Today 沿用现有 `#today-overlay` 原生 `<dialog>`，不新增页面、路由或第二覆盖层。

- 桌面：从左上 Today 入口展开为左对齐玻璃面板，宽 420px，高度不超过 85vh，距左/顶使用 `--space-lg`，人物主体在右侧保持可见。
- 390×844：受限 Bottom Sheet，最大 85dvh，顶部保留场景感知区域。
- 面板只允许内部 `.today-scroll-area` 滚动，打开时禁止背景滚动穿透。
- 背景材质参考 `rgba(10,12,16,0.65)` 与不高于 12px 的克制 backdrop blur，最终数值以截图审查为准。

## 3. 打开、关闭与焦点

- 使用 `showModal()`，依靠原生 modal focus containment。
- 打开后焦点落到 44×44 关闭按钮或首个真实操作按钮。
- 支持 Escape、可见关闭按钮和移动端辅助下滑手势；手势绝不是唯一关闭方法。
- 关闭后焦点返回 `#today-portal`。
- 不在 `<li>` 上添加 `tabindex` 或点击处理；交互必须使用真实 `<button>`。

## 4. 内容优先级算法

`GET /api/today` 经安全 adapter 后形成五类，按以下固定顺序扫描：

1. Active：`activeActivities`；
2. Time-bound：`calendarEvents`；
3. Intentions：`dueTasks` 与 `routines`；
4. Carried Over：`overdueTasks` 与 `openTasks`；
5. Completed：`completedTasks`。

规则：

- 非空类别不超过 4 个时全部展示。
- 五类均非空时，默认折叠 Completed，以低显著性的“+N 已收集光影”按钮在原位展开。
- 每区块最多展示 3 条，余量使用低显著性 `+N` 真实按钮。
- `+N` 只能在同一 dialog 内内联展开，或进入具有明确返回按钮的 dialog 内子视图；禁止页面跳转、新路由或新覆盖层。
- 全空时只显示单一留白状态，不为每个类别重复显示空文案。

## 5. 概念组件

- `TodayHeader`：标题、格式化 `<time>`、可选手动刷新按钮、关闭按钮。
- `TodayClusters`：1–4 个语义 `<section>`，标题为 `<h3>`，内容为 `<ul>`。
- `TodayItem`：纯摘要为文本；打开详情/状态操作使用真实按钮。
- `InlineDisclosure`：同一类别余量展开/折叠。
- `TimelineReveal`：显式加载时间线的按钮。
- `TimelineSubview`：同 dialog 内的最新优先时间线与返回按钮。
- `LocalStatePanel`：首次加载、空态、错误、重试等局部状态。
- `TodayStatusRegion`：短句 `aria-live="polite"`；不得包裹长列表。

## 6. 安全 Today ViewModel

View 只消费有限、纯文本、定长的展示模型。建议形状：

```text
TodayViewModel
  date: valid local date | null
  activeActivities: TodayItem[]
  calendarEvents: TodayItem[]
  dueTasks: TodayItem[]
  routines: TodayItem[]
  overdueTasks: TodayItem[]
  openTasks: TodayItem[]
  completedTasks: TodayItem[]

TodayItem
  key: opaque in-memory key
  kind: finite enum
  status: finite enum | unknown
  title: bounded plain text
  timeLabel: formatted safe string | null
  isInteractive: boolean
```

- HTML、富文本与未知嵌套结构全部拒绝。
- 日期必须有效，否则为 `null`；本地化和时区由 formatter 负责。
- `metadata`、`action_url`、source ID、evidence、日记正文和未知字段不得进入 ViewModel。
- 不透明 ID 仅在内存中关联行为，不输出到可见文本、tooltip 或错误信息。

## 7. Timeline

- 默认不请求 `/api/timeline`；只有用户明确展开时才加载。
- 安全模型仅含 `id`、有限 `kind`、`formattedTime`、安全 `title`。
- 忽略 `action_url`、source ID、证据与未知 kind。
- 与当前端点一致，最新记录排在最前。
- 可显示安全的日记标题/类型，绝不显示正文。
- 时间线列表不设置 `aria-live`；完成或失败只在短状态区域播报一次。
- 不轮询、不在窗口聚焦时刷新、不显示“刚刚/5 分钟前”等同步时间。

## 8. 缓存与刷新体验

- 首次打开请求 `/api/today`。
- 会话内重复打开先显示稳定缓存，不在打开时并发请求各资源集合。
- 如果保留手动刷新，它是首次成功后才可用的低显著性真实按钮，无上次同步时间。
- 刷新 pending 时旧数据完全可读；暂时禁止写操作，焦点保持原位。
- 刷新失败时保留旧数据，不模糊、不清空，只给局部安全重试提示。
- 首次失败时只在 Today 面板内显示错误，主场景保持可见。
- 网络恢复只刷新当前可见且已加载的数据，不批量预取其他空间。

## 9. 确定性状态矩阵

| 状态 | 可见内容 | 允许操作 | 焦点 |
| --- | --- | --- | --- |
| closed/unloaded | 仅主场景 | 打开 Today | Today 入口 |
| first-loading | 静态或 4–6s 极慢骨架，主场景仍可感知 | 关闭 | 关闭按钮 |
| ready-populated | 1–4 个类别 | 阅读、展开、真实次级入口、timeline、刷新、关闭 | 保持操作处 |
| ready-sparse/empty | 稀疏内容或单一留白文案 | timeline、刷新、关闭 | 关闭/刷新 |
| adapter-partial-safe | 只显示验证成功类别，损坏类别静默丢弃 | 同 ready | 保持操作处 |
| first-error/offline | 局部安全错误，无骨架 | 重试、关闭 | 重试按钮 |
| cached-refresh-pending | 旧数据完整可读，刷新按钮安静 pending | 阅读、关闭；写入暂禁 | 原位 |
| cached-refresh-error | 旧数据完整可读，局部失败提示 | 阅读、重试、关闭 | 原位并短播报 |
| timeline-loading | 原 Today 保留，timeline 局部静态骨架 | 返回、关闭 | 返回按钮 |
| timeline-ready/empty | 最新优先列表或单一空态 | 返回、滚动、关闭 | 首项/返回 |
| timeline-error/retry | timeline 局部错误 | 重试、返回、关闭 | 重试 |
| reduced-motion | 对应状态的静态视觉 | 同对应状态 | 同对应状态 |

`GET /api/today` 是单一聚合请求；“partial”仅指 adapter 丢弃非法类别/条目，不是假装多个独立接口部分成功。

## 10. 视觉和动效参数

- 面板宽 420px、最大 85vh/85dvh。
- 区块间距 24px、项目间距 12px。
- 标题约 1.125rem、正文 0.95rem、次级信息 0.85rem。
- 边框参考 `rgba(255,255,255,0.08)`，Active 参考冰蓝 `#a5c4d4`。
- 加载若有透明度呼吸，周期为 4–6s；完全静态骨架无时长要求。
- Reduced Motion 下无持续呼吸和位移，保留静态层级。
- 禁止红色、Spinner、文字脉冲、粒子爆发、高频扫光和破坏性模糊。

## 11. 响应式、长内容和触控

- 使用 `env(safe-area-inset-top/bottom)`。
- 所有可交互热区至少 44×44。
- 项目标题使用 `overflow-wrap:anywhere` 与 `word-break:break-word`；默认最多两行，展开后可读全文。
- 无水平滚动；面板内部持有纵向滚动。
- 软键盘出现时调整 dialog 可用高度，关闭/返回与当前输入保持可见。
- 下滑关闭应有距离阈值和取消路径，不能妨碍面板内滚动。

## 12. 反模式与隐私

- 无 checkbox 墙、表格/卡片墙、完成比、红色逾期、倒计时焦虑或统计徽章。
- 无 Toast、全局 Banner、系统权限提示、通知偏好或 DND；这些属于 S4/S5。
- 无自动刷新、后台轮询或并发加载所有生活流集合。
- 不把 stable cache 在错误时清空或模糊。
- 不展示 diary body、metadata、source ID、action URL、内部错误或原始 schema。

## 13. 写入边界

- 本文档只定义 Today 读空间与次级入口，不定义具体表单。
- 用户直接发起的任务完成、习惯打卡等操作可以调用对应 CRUD/action 接口，但必须非乐观、局部 pending、成功后提交稳定数据、失败后恢复输入与原状态。
- 陪伴者主动提出并影响现实生活的行动必须走 `/api/actions/preview` → 明确确认 → `/api/actions/confirm`。

## 14. 浏览器与截图验收

必须覆盖：

1. 桌面 populated：左侧 420px 面板、人物脸部可见、五类折叠算法正确。
2. 390×844 populated：Bottom Sheet、44px 触控、安全区和内部滚动。
3. 桌面/移动 empty：单一留白态，无重复空区块。
4. first error/offline：局部错误，场景不被替换。
5. cached refresh error：旧数据可读，无遮挡、无清空。
6. timeline loading/ready/empty/error/retry：只在显式触发后出现。
7. 键盘 Tab/Enter/Escape、焦点可见、关闭后返回入口。
8. 模拟软键盘：面板和当前控件不被顶出。
9. 超长中文和无空格英文：无水平溢出。
10. reduced-motion：无呼吸或位移动画。
11. 安全：DOM/状态/日志不含拒绝字段。

## 15. 移交 S3 Design 02/03

后续文档必须解决：

- 单项详情、创建和编辑控件；
- 任务步骤/状态、习惯打卡、活动生命周期、提醒/日程操作；
- 日记草稿、编辑、保存与隐私真实表达；
- 普通 CRUD 的 pending/error/retry 和并发防护；
- companion action preview/confirm；
- 表单验证、草稿恢复、冲突与重试语义。
