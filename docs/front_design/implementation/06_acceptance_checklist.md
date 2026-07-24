# 06 Acceptance Checklist

## 视觉与沉浸

- [ ] 首屏是人物 + 空间 + 字幕 + 凝露输入。
- [ ] 不存在三栏工具台。
- [ ] 不存在密集聊天气泡流。
- [ ] 不存在 SaaS 顶部导航或卡片墙。
- [ ] 视觉方向符合晶格温室。
- [ ] 没有圣经、天平、审判、圣女、宗教/法庭道具。

## Chat / Presence

- [ ] `POST /api/chat` 可用。
- [ ] `role_action` 显示为动作/字幕辅助层。
- [ ] `reply` 显示为主字幕。
- [ ] `role_thinking` 默认折叠。
- [ ] `system_thinking` 不进入 DOM。
- [ ] `GET /api/state` 或 chat 返回的 `presence` 能驱动状态光。

## Memory / Outbox

- [ ] `/api/outbox` 可达。
- [ ] `/api/outbox/feedback` 可用。
- [ ] `/api/outbox/receipt` 可用。
- [ ] `/api/memory` 可达。
- [ ] memory threads / links / evidence 可查看。
- [ ] memory update / forget / export 有确认或清晰反馈。

## Today / Life Flow

- [ ] `/api/today` 可达。
- [ ] `/api/timeline` 可达。
- [ ] reminders 创建、snooze、complete、cancel 可用。
- [ ] calendar events 创建、编辑或删除路径可用。
- [ ] notification settings 可保存。
- [ ] tasks 创建、开始、完成、阻塞、取消可用。
- [ ] routines checkin 可用。
- [ ] activities start / pause / resume / complete / cancel 可用。
- [ ] diary draft / edit / delete 可用。
- [ ] actions preview / confirm 可用。

## 安全与边界

- [ ] DND / quiet hours 下主动联系静默。
- [ ] daily_limit / allowed_kinds 有可理解呈现。
- [ ] 高风险状态不制造恐慌。
- [ ] prompt / trace / ledger / jobs 不进入普通主体验。
- [ ] debug 入口默认深层隐藏。

## 移动端与可访问性

- [ ] 390x844 首屏可用。
- [ ] 移动端键盘不遮挡字幕和输入。
- [ ] bottom sheet 可关闭且有 scroll lock。
- [ ] 所有环境物件入口有 aria-label。
- [ ] 键盘可操作主要流程。
- [ ] focus 状态清晰。
- [ ] `prefers-reduced-motion` 生效。

## 性能与工程

- [ ] mock 服务可启动。
- [ ] 首屏不依赖外部 CDN。
- [ ] 动效不造成明显掉帧。
- [ ] fetch 错误有局部恢复。
- [ ] 没有未处理 Promise rejection。
- [ ] 单文件结构仍可维护。
