# Batch 3A：响应式、动效、可访问性与安全隐私边界

作为「栖光 luminous」的主设计师，本规范旨在确保“晶格温室”主题在多端设备上保持沉浸感与陪伴感，同时建立严密的系统安全防线与无障碍体验标准。本规范完全基于 Vanilla HTML/CSS/JS 技术栈制定。

---

## 1. 响应式策略总览

“晶格温室”的响应式设计不只是改变布局，而是**“视角的推拉与焦点的转移”**。

*   **桌面/笔记本 (Viewport > 1024px)：** 广角全景沉浸。`ImmersiveStage` 充满全屏，`CompanionFigure` 居中偏右，左侧留白给 `Task/Routine/Activity Controls`，`MemoryConstellation` 悬浮于顶部空间。
*   **平板/窄高屏 (Viewport 768px - 1024px)：** 中景视角。两侧面板变为半透明悬浮层，`CompanionFigure` 居中。
*   **手机竖屏 (Viewport < 768px)：** 特写视角。UI 极简化，隐藏环境装饰。`TodaySheet` 和 `DiaryReview` 降级为 Bottom Sheet（底部抽屉）。
*   **手机横屏 (Landscape)：** 电影模式。隐藏所有非必要控件（AirInput 变为单行悬浮），仅保留 `CompanionFigure` 和 `SubtitleDialogue`，最大化陪伴感。
*   **低端设备降级：** 禁用 `backdrop-filter`（毛玻璃），以半透明纯色替代；关闭复杂的 CSS 阴影与多层光晕，保留基础的透明度与位移变化。

---

## 2. 移动端交互规范

*   **安全区域 (Safe Area)：** 全面适配 `env(safe-area-inset-*)`。顶部留出刘海/灵动岛空间，底部输入框 `AirInput` 必须在 Home Indicator 之上。
*   **键盘防遮挡 (Virtual Keyboard)：**
    *   使用 Visual Viewport API 监听键盘弹出。
    *   **核心规则：** 绝对不允许字幕 (`SubtitleDialogue`) 和输入框 (`AirInput`) 遮挡人物脸部（屏幕上半部分 40% 区域）。
    *   键盘弹出时，`CompanionFigure` 触发 CSS `transform: translateY(-10vh) scale(0.95)` 向上微调，输入框紧贴键盘顶部。
*   **触控命中区 (Touch Targets)：** 所有可交互物件（如 `OutboxGlint`, `NotificationBoundary` 的关闭按钮）物理点击区域不得小于 `44px * 44px`。视觉上可以小，通过 `padding` 或伪元素扩大点击区。
*   **手势与滚动锁定 (Gestures & Scroll Trap)：**
    *   全局禁用浏览器默认下拉刷新：`overscroll-behavior-y: none;`。
    *   Bottom Sheet 支持向下 Swipe 关闭（监听 `touchstart`, `touchmove`, `touchend` 计算 Y 轴位移）。
    *   浮层打开时，给 `<body>` 添加 `overflow: hidden` 防止底层 Stage 滚动。

---

## 3. 动效与状态驱动

坚持“克制、呼吸感、自然物理”的动效原则，全部由 Vanilla CSS/JS 实现。

*   **状态驱动映射 (Presence/State)：**
    *   `state: idle` -> `PresenceHalo` 缓慢呼吸（`transform: scale(1) to scale(1.05)`，时长 6s，`ease-in-out`，无限循环）。
    *   `state: thinking` -> `CompanionFigure` 增加轻微焦外虚化（`filter: blur(2px)`），`OutboxGlint` 产生流光效果（CSS `linear-gradient` background-position 动画）。
    *   `state: speaking` -> `SubtitleDialogue` 逐字浮现（通过 JS 拆分文本包裹 `<span>`，依次添加带有 `opacity: 1; transform: translateY(0)` 的 class，间隔 30ms）。
*   **动效节奏 (Timing & Easing)：**
    *   入场 (Enter)：`0.4s cubic-bezier(0.2, 0.8, 0.2, 1)`（减速进入，轻盈）。
    *   退场 (Exit)：`0.25s cubic-bezier(0.8, 0, 1, 1)`（加速离开，干脆）。
*   **性能限制：** 只对 `transform` 和 `opacity` 进行动画处理。避免对 `width/height/top/left` 做过渡。

---

## 4. prefers-reduced-motion 与低性能降级

尊重用户的生理需求，防止晕动症。

*   **CSS 媒体查询拦截：**
    ```css
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
      /* 针对特定状态的替代反馈 */
      .presence-halo { transform: none !important; opacity: 0.8; }
    }
    ```
*   **降级策略：**
    *   禁用 `PresenceHalo` 的呼吸缩放，改为静态发光。
    *   禁用 `MemoryConstellation` 的星空漂浮动画。
    *   Bottom Sheet 的滑出改为瞬间的 `display: block` 与简单的透明度渐变 (Crossfade)。

---

## 5. 声音与触觉建议

*   **Web Audio 规范：**
    *   **严格禁止自动播放 (No Autoplay)：** 必须由用户首次交互（如点击“进入温室”）解锁 AudioContext。
    *   **闪避机制 (Ducking)：** 当 `reply` 触发 TTS 语音时，JS 需控制背景环境音（如温室白噪音）的 GainNode 缓慢降至 20%，语音结束后恢复至 100%（Side-chain 模拟）。
*   **触觉反馈 (Haptics)：**
    *   仅在支持 `navigator.vibrate` 的移动端启用。
    *   微小交互（点击 `AirInput` 发送）：`navigator.vibrate(10)`（极其轻微的震动）。
    *   状态变更（`Task` 完成）：`navigator.vibrate([20, 50, 20])`（双重轻震，模拟心跳）。

---

## 6. 可访问性规范 (A11y)

*   **环境化 UI (Diegetic UI) 的语义化：**
    *   像 `MemoryConstellation`（记忆星图）这样的视觉化组件，必须包含 `.sr-only`（屏幕阅读器专用）的文本描述。
    *   例如：`<button class="star-node" aria-label="查看 10 月 12 日的记忆：第一次谈论电影"></button>`。
*   **焦点管理 (Focus Management)：**
    *   使用自定义的 `:focus-visible` 样式（如柔和的白色外发光 `box-shadow: 0 0 0 2px rgba(255,255,255,0.6)`），不破坏晶格温室的视觉一致性。
    *   打开 `TodaySheet` 抽屉时，JS 需将焦点 Trap（锁定）在抽屉内部，关闭时将焦点交还给触发按钮。
*   **字幕可读性：** `SubtitleDialogue` 必须满足 WCAG AA 级对比度。在复杂的背景下，字幕容器需加上底部的文字阴影或极度柔和的暗色渐变遮罩。
*   **ARIA 实时播报：**
    *   字幕区域需设置 `aria-live="polite" aria-atomic="true"`，确保屏幕阅读器能读出 AI 的新回复。

---

## 7. 弱网、慢模型与服务端错误体验

保持陪伴感，不制造系统崩溃的恐慌。

*   **慢模型/长思考：** 超过 3 秒未返回 `reply` 时，不使用传统的 Loading 菊花图。`PresenceHalo` 转为缓慢的脉冲闪烁，并随机显示安抚性提示（如：“正在整理思绪...”），保持环境的宁静感。
*   **弱网/断网 (Offline)：** 监听 `window.addEventListener('offline', ...)`。界面不报错，而是让环境光线微微变暗，`SubtitleDialogue` 显示：“温室的信号似乎被云层遮挡了，我在这里陪你等风停。”
*   **局部数据失败：** 如果 `memory` 节点获取失败，不弹窗报错，仅隐藏 `MemoryConstellation` 入口，保证主聊天流正常运转。

---

## 8. 安全与隐私边界

这是最严厉的防线，确保底层逻辑与高风险内容不侵蚀用户的信任。

*   **`system_thinking` 前端绝对隔离：**
    *   在 `fetch` 响应的 JSON 解析阶段，立即执行清洗：
        `if ('system_thinking' in payload) { delete payload.system_thinking; }`
    *   **严禁**任何代码路径将该字段拼接到 DOM 或 `console.log` 中。
*   **`role_thinking` 的折叠呈现：**
    *   作为角色的“内心戏”，默认折叠，显示为“...”或“（思考中）”。
    *   点击展开后，样式必须与主 `reply` 明显区分：使用更小的字号、斜体、降低透明度（如 60%），传达“这是过程，不是最终对话”。
*   **高风险状态 (Safety Flags) 降噪：**
    *   当 API 返回高风险标记时，**不要**显示红色的警告框（避免刺激用户）。
    *   界面色调自动过渡为冷静的冷白光（Cool White）。
    *   暂停一切主动搭话 (`proactive`)。
    *   在输入框侧边提供一个低调的盾牌 Icon（`NotificationBoundary`），点击展开温和的边界提示与心理干预/审计链接。
*   **隐私模式 (Privacy Screen)：**
    *   当页面通过 Page Visibility API 侦测到 `document.hidden` 或用户长时间无操作（10分钟）时，整个 Stage 加上 `backdrop-filter: blur(10px)`，保护屏幕内容不被旁人窥视。

---

## 9. Batch 3A 自检清单

请在合并代码前，逐项确认以下 16 条标准：

**响应式与移动端**
- [ ] 1. 桌面端浏览器缩放至窗口宽度 390px 时，UI 能够平滑过渡到移动端布局，无横向滚动条。
- [ ] 2. 在 iOS Safari/Android Chrome 唤起虚拟键盘时，输入框准确上浮，且字幕不遮挡人物核心区域（面部）。
- [ ] 3. 所有可点击元素（包括关闭图标、历史记忆点）的物理点击区达到 44x44px。
- [ ] 4. 移动端 Bottom Sheet 展开时，背景 `<body>` 无法被滚动（Scroll Trap 生效）。

**动效与性能**
- [ ] 5. 开启操作系统的“减弱动态效果”后，呼吸动画停止，滑出动画变为透明度渐变。
- [ ] 6. 核心动画（呼吸、抽屉滑出）仅使用了 `opacity` 和 `transform` 属性，无重排（Reflow）触发。

**可访问性 (A11y)**
- [ ] 7. 仅使用键盘 (Tab/Enter/Space) 能够顺畅完成：输入消息、发送、打开今日面板、关闭面板的操作。
- [ ] 8. 键盘聚焦时，元素有清晰且符合主题的 `:focus-visible` 样式。
- [ ] 9. AI 的回复字幕容器设置了 `aria-live="polite"`。
- [ ] 10. `MemoryConstellation` 等非文字视觉组件，拥有完整的 `.sr-only` 文本或 `aria-label`。

**异常与降级**
- [ ] 11. 拔掉网线触发 `offline` 事件时，界面不会白屏或弹出原生 `alert`，而是进入安抚性的断网状态。
- [ ] 12. 模拟 API 响应延迟 > 5秒时，界面展示平缓的思考状态，无焦躁感。

**安全与隐私**
- [ ] 13. 源码全局搜索，确认没有任何逻辑将 `system_thinking` 渲染到 DOM 中。
- [ ] 14. `role_thinking` 内容默认处于折叠状态，且视觉层级明显低于 `reply`。
- [ ] 15. 模拟高风险状态返回时，界面不会出现红色警告，而是切换为冷静光效并提供低调的审计入口。
- [ ] 16. 切换浏览器标签页（触发 visibilitychange）时，界面能自动进入模糊隐私模式。
