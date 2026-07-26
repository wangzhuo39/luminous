你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮输出 Batch 3A：响应式、动效、可访问性、安全隐私边界。

方向：晶格温室。首屏沉浸，移动端可用，动效克制，安全隐私不破坏陪伴感。当前技术栈是 Vanilla HTML/CSS/JS 静态 index.html。

已定关键组件：ImmersiveStage、CompanionFigure、PresenceHalo、SubtitleDialogue、AirInput、OutboxGlint、MemoryConstellation、TodaySheet、Task/Routine/Activity Controls、DiaryReview、NotificationBoundary。

安全约束：POST /api/chat 返回 role_thinking、role_action、reply、presence、memory、state、prompt、proactive；system_thinking 已后端剥离，前端仍必须防止任何 system_thinking 字段进入 DOM。高风险状态要降噪、提示边界、保留审计入口，但不制造恐慌。

请输出中文 Markdown，结构：

# Batch 3A：响应式、动效、可访问性与安全隐私边界

## 1. 响应式策略总览
- 桌面、笔记本、手机、横屏、窄高屏、低端设备的体验目标。
- 哪些沉浸效果保留，哪些降级。

## 2. 移动端交互规范
- 390x844 竖屏、键盘打开、safe-area、bottom sheet、手势、触控命中区、滚动锁定、多层浮层关闭。
- 字幕和输入不遮挡人物脸部的规则。

## 3. 动效与状态驱动
- MVP 静态 HTML/CSS/JS 可实现动效清单。
- presence/state 驱动光线、雾度、镜头、字幕、输入、入口物件。
- 给动画时长、easing、节奏、性能限制。

## 4. prefers-reduced-motion 与低性能降级
- CSS/JS 策略、替代反馈、禁用哪些动效、保留哪些状态提示。

## 5. 声音与触觉建议
- Web Audio 可选项、side-chain/ducking 思路、哪些声音禁止默认播放。
- 移动端触觉后续扩展建议。

## 6. 可访问性规范
- 键盘导航、焦点顺序、ARIA、语义结构、对比度、字幕可读性、屏幕阅读器、错误提示。
- 对 diegetic UI 物件如何提供可理解名称和操作。

## 7. 弱网、慢模型与服务端错误体验
- loading、timeout、retry、offline、部分数据失败、轮询失败。
- 如何保持沉浸不误导用户。

## 8. 安全与隐私边界
- system_thinking 前端防线。
- role_thinking 折叠/安全呈现原则。
- prompt/trace/debug 不进入普通用户主体验。
- 高风险状态、DND/quiet hours、主动联系克制、隐私屏幕/模糊模式。

## 9. Batch 3A 自检清单
14-20 条。

要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
