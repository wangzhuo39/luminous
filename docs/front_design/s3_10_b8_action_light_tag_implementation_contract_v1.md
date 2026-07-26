# S3 B8 Action 光签实现契约 v1

> 状态：已实现并完成最终文档收口（2026-07-26）
> 日期：2026-07-26

## 1. 目标与触发边界

B8 交付可注入的 Proposal → Preview → Confirm 光签，但不伪造生产 proposal 来源。当前 `/api/chat` 没有 proposal 字段，因此：

- 生产模式不暴露触发器；
- fixture 浏览器测试通过 `window.__luminousActionFixture.propose()` 注入已知 proposal；
- 不提供用户手写 action/payload 的编辑器；
- 未来只需把正式、已过调用方检查的 proposal 接入 `injectProposal()`。

## 2. 安全与状态

- 前端先按五类 action 严格 allowlist/字段归一化，再调用 preview。
- complete_task/checkin_routine 必须映射到已加载的安全 VM；失败时不发 preview，不抓取、不显示 ID。
- ActionPreviewVM 的 previewKey/requestSnapshot 只留在控制器内存；View 只读取 summaryLines。
- preview 与 confirm 使用同一冻结 snapshot；confirm transport 额外只添加 `confirmed:true`。
- 状态：idle → proposal → previewing → preview_ready → confirming → success；preview/confirm 分别有错误重试；取消本地收起。
- confirming 期间确认和婉拒均禁用；重复点击由 operation gate 拒绝。
- abort/过时响应不更新状态，也不宣称服务端未执行。

## 3. 五类 action

- create_task：title 必填；只允许合法 priority、ISO due_at。
- complete_task：隐藏 task_id，摘要使用已加载 TaskVM title。
- start_focus_session：只允许 title，忽略 kind。
- checkin_routine：隐藏 routine_id；可选 bounded note。
- draft_diary：可选合法日期，不接受 title；成功后进入已持久化 DiaryEditor，后续保存走 PATCH。

## 4. 模块

- `action-state.js`：allowlist、纯状态图、proposal 归一化、安全错误。
- `action-controller.js`：preview/confirm gate、Abort、snapshot 一致、结果提交。
- `action-view.js`：只用 textContent 渲染安全摘要和状态动作。
- `app-state.js#commitConfirmedActionResult`：把安全确认结果写入相应资源；日记草稿进入 editor。
- `main.js`：组合组件；仅 fixture 模式提供测试注入钩子。
- `index.html`：对话与输入水面之间的语义 section，不是 modal。

## 5. 视觉

光签是一枚从对话水面折出的半透明窄签：折光细边、少量物理阴影、冷白/冰蓝、克制呼吸。出现最多位移 4px；pending 折光周期 6s；reduced-motion 取消循环和位移。光签出现时实体门户退后且不可交互，避免移动端叠压。

## 6. 验收定义

- 五类 allowlist、未知字段剔除、缺失映射、snapshot 一致、双击、重试与安全 store 更新通过。
- preview_ready、success、cancelled、missing mapping、draft diary editor、mobile/reduced-motion 有浏览器证据。
- DOM/console 不出现 opaque ID 或原始 payload。
- S2 chat 行为不变，生产模式无 proposal 触发器。
