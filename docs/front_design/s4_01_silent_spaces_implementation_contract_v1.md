# S4 静默空间联通实施契约 v1

> 日期：2026-07-26
> 范围：Outbox、Memory、通知偏好、只读 DND、Privacy 视觉与交互边界

## 1. 结论

S4 采用三个既有环境入口，不新增路由或顶层页面：来信是暖白折页，记忆是冷紫冰蓝晶体，隐私是低对比雾面帘。它们继续继承晶格温室 v2 的场景定位、材质、视差暂停、移动底部 sheet 与 reduced-motion 策略。

真实后端审计后，用户态允许接入：

- `GET /api/outbox`、`POST /api/outbox/receipt`、`POST /api/outbox/feedback`；
- `GET /api/memory`、`POST /api/memory/update`、`POST /api/memory/forget`；
- `GET/PATCH /api/settings/notifications`；
- `GET /api/state` 中只读的 `dnd_until`。

普通界面明确禁止读取或渲染 memory threads/links/evidence、ledger、trace、prompt、export，以及 Outbox 的 score/reason/payload/anchor/idempotency 等内部字段。当前后端没有独立 DND 写接口，因此 UI 只显示真实状态，不伪造 DND 操作。

## 2. 分批与刷新策略

本批次一次完成三个空间，但保持独立状态边界：

1. 来信首次打开懒加载，当前会话缓存；不轮询、不制造红点焦虑。失败时显示“重新展开”，成功内容保留。回执和反馈逐项 pending，失败不移除信笺。
2. 记忆首次打开保持 idle，不列出全部记忆；用户提交查询后才请求。修订与软忘却都内联确认，服务端成功前不乐观覆盖或移除。
3. 隐私首次打开同时读取通知偏好和安全状态；字段变化后才允许保存。初次加载失败不展示默认值冒充真实设置；保存失败保留草稿和既有值。

没有后台刷新、SSE、WebSocket 或推送契约。后续若引入刷新，只允许显式用户刷新或经过功耗/打扰评审的低频策略。

## 3. 安全展示模型

```text
OutboxItemVM
  key, body, status, kind, occurredAt

MemoryItemVM
  key, content, kind, occurredAt

PrivacyVM
  enabled, dailyLimit, quietStart, quietEnd, allowedKinds, dndUntil
```

`key` 只用于事件闭包和 `data-key`，不作为可见文字。`scene-environment.js` 只接收 `memoryCount`、`outboxUnread`、`dnd` 三个聚合值，不接收正文、key 或 raw response。

## 4. 文件职责

- `services/silent-spaces-api.js`：相对 `/api/` 路径和最小请求体；
- `adapters/silent-spaces-adapter.js`：逐字段白名单、枚举和长度限制；
- `features/silent-spaces/silent-spaces-controller.js`：懒加载、Abort、pending gate、错误恢复、非乐观提交；
- `features/silent-spaces/silent-spaces-view.js`：只渲染安全 VM，使用文本节点；
- `features/silent-spaces/silent-spaces-fixture.js`：零网络可交互 fixture；
- `styles/silent-spaces.css`：Gemini 视觉蓝图与复审修正；
- `main.js`：选择 API/fixture DataSource，并只把安全聚合值交给环境层。

## 5. 视觉与交互规则

- 来信不是通知中心；使用折页、不规则边缘、低饱和暖白和“轻轻收下”。
- 记忆不是搜索后台；输入框使用非对称晶体切面，结果只在主动凝视后出现。
- 隐私不是设置控制台；原生控件经凝露/切面处理，DND 状态为说明文字。
- 危险操作不再开第二层 modal；“忘却”在原晶体内展开确认。
- 所有状态都有文字和 `aria-live`；移动可见按钮高度至少 44px。
- reduced-motion 取消空间和控件动画，但不取消状态反馈。

## 6. Gemini 记录与复审

全部请求/响应位于项目外：

- 视觉蓝图：`/home/wz/gemini-api-traces/20260726T084834.237423Z_luminous-s4-silent-spaces-visual-blueprint-v1_ea46e2ba/`
- 四图多模态审阅：`/home/wz/gemini-api-traces/20260726T090302.238320Z_luminous-s4-silent-spaces-multimodal-audit-v1_8bbccc61/`

多模态初审 88/100、无 P0、Conditional Pass。其三个 P1 已落实：隐私控件去 SaaS 化、反馈文案改为“我会记得”、记忆搜索框增加非对称晶体切面；移动反馈间距和 disabled 保存按钮权重也已修正。

## 7. 验收门槛

- Adapter 单测证明内部字段不会进入 VM；
- API 单测证明路径、方法和请求体精确，非法输入在网络前拒绝；
- Chromium 覆盖桌面来信、记忆修订/忘却、隐私保存、移动 reduced-motion、真实 API 500→重试与 no-leak；
- 晶格温室 v2 浏览器回归继续通过；
- `git diff --check` 通过。
