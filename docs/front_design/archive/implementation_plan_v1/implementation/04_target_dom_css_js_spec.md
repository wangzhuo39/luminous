# 04 Target DOM / CSS / JS Spec

## 目标 DOM 分区

建议在 `index.html` 中形成如下概念分区：

```html
<div id="appRoot" class="luminous-app">
  <main id="immersiveStage" class="immersive-stage">
    <section class="stage-background"></section>
    <section class="environment-fx"></section>
    <section class="companion-figure"></section>
    <section class="presence-halo"></section>
    <section class="subtitle-dialogue"></section>
    <form class="air-input"></form>
    <nav class="diegetic-portals"></nav>
  </main>

  <section id="memoryConstellation" class="overlay-layer"></section>
  <section id="todaySheet" class="sheet-layer"></section>
  <section id="privacyAuditDrawer" class="audit-layer"></section>
  <section id="debugTracePanel" class="debug-layer"></section>
</div>
```

这不是要求 Gemini 逐字照抄，而是目标结构约束。

## z-index 层级

- background：0-10
- environment fx：20-40
- companion figure：50-70
- presence halo：80-90
- subtitle dialogue：100-120
- air input：130-150
- diegetic portals：160-180
- overlay layer：300-399
- sheet layer：400-499
- audit/debug layer：700-899
- emergency/risk boundary：900+

## CSS Token 分组

至少包含：

- color background
- color moon / ice / mist
- color warm reminder
- color risk / danger
- text primary / secondary / faint
- glass opacity
- line subtle
- focus ring
- shadow soft
- motion duration
- easing
- breakpoint values

## 关键组件

- `ImmersiveStage`
- `CompanionFigure`
- `PresenceHalo`
- `SubtitleDialogue`
- `AirInput`
- `OutboxGlint`
- `MemoryConstellation`
- `TodaySheet`
- `TaskControls`
- `RoutineControls`
- `ActivitySession`
- `DiaryReview`
- `NotificationBoundary`
- `PrivacyAuditDrawer`
- `DebugTracePanel`

## JS 组织建议

仍在单文件中实现，但按区域组织：

1. DOM selectors
2. state store
3. API helpers
4. render helpers
5. chat / presence module
6. outbox module
7. memory module
8. today / schedule module
9. life-flow module
10. audit / debug module
11. event binding
12. boot sequence

## 状态 Store 建议

```js
const appState = {
  chat: {},
  presence: {},
  outbox: {},
  memory: {},
  today: {},
  notifications: {},
  overlays: {},
  debug: {}
};
```

## 渲染边界

- API helper 只负责请求和错误归一。
- render 函数只接受已归一的数据。
- DOM 写入必须 escape 文本内容。
- `system_thinking` 字段进入归一函数时直接丢弃。

## 移动端断点

- desktop：`>= 1024px`
- compact laptop：`720px-1023px`
- mobile：`< 720px`
- 重点验收：`390x844`

## reduced motion

必须支持：

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.001ms;
    transition-duration: 0.001ms;
  }
}
```

保留静态状态提示，不依赖动效传递唯一信息。
