# 02 Existing Frontend Inventory

## 当前入口

`/home/wz/luminous/apps/companion-web/companion-ui/index.html`

当前文件约 1600 行，包含 HTML、CSS、Vanilla JS 和所有前端逻辑。

## 当前能力

现有原型已经覆盖：

- 聊天发送与响应
- presence 状态更新
- role_action / role_thinking / reply 渲染
- outbox 主动联系
- reminder / calendar event
- notification preferences
- life-flow 浮层
- task / routine / activity
- diary draft
- actions preview / confirm

## 当前主要问题

- UI 偏三栏工具台。
- 功能入口显性且工具化。
- 聊天区域仍像传统消息流。
- life-flow 是后来注入的独立浮层，视觉风格与主界面割裂。
- 右侧记忆/日程/通知能力压迫主体验。

## 实现时必须保留的现有逻辑

- `POST /api/chat` 调用与错误处理
- outbox feedback / receipt
- reminders create / snooze / complete / cancel
- calendar events create / delete
- notification settings patch
- today / timeline / tasks / routines / activities / diary entries
- actions preview / confirm

## 可以替换的部分

- HTML 布局结构
- CSS 视觉系统
- 三栏容器
- chat bubble 样式
- sidebar / memory panel 的默认显性呈现
- life-flow 注入面板的视觉和挂载方式

## 风险点

- 不要删除 API 函数后忘记重接 UI。
- 不要把 `role_thinking` 默认展开。
- 不要让 `system_thinking` 进入 DOM。
- 不要只做视觉替换而丢失 reminders/calendar/life-flow。
