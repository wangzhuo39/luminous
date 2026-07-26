# Luminous S2 环境与状态层视觉重构设计规范

> 状态：实现基线 v1
> 设计：Gemini；工程约束审查与修订回合：Codex
> 原始设计 trace：`/home/wz/gemini-api-traces/runs/20260724T200121.440717Z_luminous-s2-environmental-state-design_5c59f3f5/`
> 修订 trace：`/home/wz/gemini-api-traces/runs/20260724T200359.669775Z_luminous-s2-environmental-design-repair_e8a57a9b/`

## 1. 设计意图与哲学映射

在「晶格温室」的隐喻中，技术状态不应打破第四面墙。网络断连、API 延迟和模型错误应被转译为物理环境的自然变化：

- Offline 是温室外起雾、光线暗淡、色彩流失，而不是划掉的圆圈。
- Submitting 是水面凝露每 5 秒一次的深长呼吸，而不是 Spinner 或急促边框。
- Scene Tone 是透过玻璃折射的环境色温。
- Error 是光影短暂失焦或水面微弱涟漪，而不是红色警报。

移除 `#connection-status`，由环境光、雾度和输入材质接管状态表达。异常状态不得干涉用户记录草稿的自由。

## 2. 状态优先级模型

1. `body[data-app-status]` 优先级最高，决定全局亮度、饱和度、雾化和遮罩。
2. `#input-surface[data-chat-status]` 只影响前景输入区。
3. `body[data-tone]` 是基础环境层，在 `ready` 或 `fixture` 时完整显现。

实现时必须把 Tone 与 App Status 拆成不同变量后组合，避免 quiet 的基础亮度错误覆盖 offline/loading/error。

## 3. 状态与视觉映射矩阵

### 3.1 App Status

| 状态 | 环境表现 | 过渡 | Reduced Motion |
| :--- | :--- | :--- | :--- |
| `loading` | `blur(6px)`、亮度 70%、极淡灰遮罩；Fixture 轮廓仍可辨 | 2s ease-in-out | 瞬间切换，保留静态视觉 |
| `ready` | 清晰、亮度 100%，由 Tone 接管 | 3s ease-out | 瞬间切换 |
| `fixture` | 与 ready 相同 | 无 | 无 |
| `offline` | 饱和度 50%、`blur(4px)`、亮度 70%、暗色遮罩 | 4s ease-in-out | 瞬间切换，保留静态去色和变暗 |
| `error` | 亮度 85%、无模糊、极弱冷灰遮罩 | 1s ease-out | 瞬间切换 |

### 3.2 Scene Tone

| Tone | 色温与光晕 |
| :--- | :--- |
| `calm` | 极淡冰蓝 `rgba(165, 196, 212, 0.1)` |
| `warm` | 淡桃/暖金 `rgba(244, 232, 209, 0.12)` |
| `quiet` | 深灰蓝 `rgba(120, 132, 141, 0.2)`，基础亮度 85% |
| `concerned` | 微弱紫罗兰 `rgba(180, 165, 212, 0.15)` |
| `unknown` | 与 `calm` 完全相同 |

### 3.3 Chat Status 与输入行为

`textarea` 禁止使用 `disabled`。只允许通过禁用发送按钮拦截发送。

| 状态 | Textarea | 发送按钮 | 输入区表现 | Reduced Motion |
| :--- | :--- | :--- | :--- | :--- |
| `idle` | 可编辑 | 按草稿有效性决定 | 1px 半透明白边 | 无变化 |
| `submitting` | `readOnly` | 等待态 | 5s 边框呼吸 | 无循环动画，保留静态高亮 |
| retryable `error` | 可编辑，保留草稿 | 允许重试 | 柔和珊瑚边框 | 无变化 |
| validation `error` | 可编辑，允许修改 | 禁用 | 暗淡边框和柔和局部提示 | 无变化 |

## 4. DOM 挂载点与拓扑

- 删除 `#connection-status` 及内部 SVG。
- 继续使用 `body[data-app-status]`、`body[data-tone]`、`#input-surface[data-chat-status]` 和 `#chat-feedback`。
- `.scene-container::before` 使用 z-index 200，承载 Tone 色温层。
- `.scene-container::after` 使用 z-index 201，承载 App Status 雾化与暗化层。

两层均位于人物 z-index 150 与对话 z-index 300 之间，因此影响背景和人物，但不降低对话、输入与入口的清晰度，也不得接收指针事件。

## 5. 视觉令牌和实现参数

```css
:root {
  --duration-presence-pulse: 5s;
  --ease-luminous: cubic-bezier(0.4, 0, 0.2, 1);
  --color-feedback-error-text: rgba(224, 186, 186, 0.85);
  --color-feedback-error-border: rgba(224, 186, 186, 0.3);
  --tone-calm: rgba(165, 196, 212, 0.1);
  --tone-warm: rgba(244, 232, 209, 0.12);
  --tone-quiet: rgba(120, 132, 141, 0.25);
  --tone-concerned: rgba(180, 165, 212, 0.15);
}

body {
  --env-tone-brightness: 1;
  --env-status-brightness: 1;
  --env-status-saturation: 1;
  --env-status-blur: blur(0px);
  --env-status-color: transparent;
  --env-tone-color: var(--tone-calm);
}

body[data-tone="calm"],
body[data-tone="unknown"] { --env-tone-color: var(--tone-calm); }
body[data-tone="warm"] { --env-tone-color: var(--tone-warm); }
body[data-tone="quiet"] {
  --env-tone-color: var(--tone-quiet);
  --env-tone-brightness: 0.85;
}
body[data-tone="concerned"] { --env-tone-color: var(--tone-concerned); }

body[data-app-status="offline"] {
  --env-status-brightness: 0.7;
  --env-status-saturation: 0.5;
  --env-status-blur: blur(4px);
  --env-status-color: rgba(10, 12, 16, 0.3);
}
body[data-app-status="loading"] {
  --env-status-brightness: 0.7;
  --env-status-blur: blur(6px);
  --env-status-color: rgba(10, 12, 16, 0.2);
}
body[data-app-status="error"] {
  --env-status-brightness: 0.85;
  --env-status-color: rgba(20, 22, 26, 0.2);
}
```

最终滤镜必须组合 `--env-tone-brightness` 与 `--env-status-brightness`，而不是让两个状态争用同一变量。`backdrop-filter` 不可用时，半透明遮罩、亮度与饱和度仍须表达异常状态。

## 6. 多端、安全区与无障碍

- `#chat-feedback` 使用 `calc(8px + env(safe-area-inset-bottom))` 预留底部空间。
- Reduced Motion 下所有环境过渡近乎瞬时，取消无限呼吸动画，保留静态高亮。
- 连接状态通过现有 `.sr-only[aria-live="polite"]` 播报；禁止用 CSS `content` 生成状态文本。
- 移动端不得因为状态反馈压缩输入目标或遮挡人物主体。

## 7. 反模式与隐私边界

- 禁止禁用 textarea；仅 submitting 时短暂 `readOnly`。
- 仅显示 AppState 提供的安全中文错误文案，不另造运行时文案，不显示原始异常或后端详情。
- 禁止纯红、高频闪烁、Spinner、Toast、Banner 和全局错误弹窗。
- 禁止过度遮蔽，loading/offline 下必须识别出初始场景。
- 不渲染诊断、prompt、analysis、memory、ledger、role thinking/action 等内部字段。

## 8. 截图验收标准

1. Desktop Ready/Warm：背景和人物出现微弱暖金色调，无断网图标，前景保持清晰。
2. Desktop Submitting：输入为 `readOnly`，边框以 5s 周期呼吸；Reduced Motion 下无循环动画。
3. Desktop Retryable Error：草稿完整恢复，可编辑，柔和珊瑚边框和安全局部文案，重试可完成一次。
4. Desktop Validation Error：输入可编辑、发送禁用、提示不刺眼。
5. Mobile Offline：背景和人物去色、起雾、暗淡；输入可编辑、发送禁用；无断网图标；安全区不拥挤。
6. 无 `backdrop-filter`：仍可通过遮罩、亮度和饱和度分辨离线态。

### 终审修订

实际截图终审发现 8px 雾化使移动端人物接近黑影，因此 Gemini 将离线模糊修订为 4px；离线输入使用 `rgba(255,255,255,0.1)` 边框和 `rgba(10,12,16,0.4)` 背景，焦点轮廓保留为 `rgba(255,255,255,0.3)`。错误焦点轮廓使用 `--color-feedback-error-text`，保持珊瑚色系并继续满足键盘可见性。

## 9. 实施批次

### Batch 1：移除反模式并修正基础反馈

- 删除 `#connection-status`。
- 将等待呼吸改为 5s。
- 柔化错误色并增加 `#chat-feedback` 安全区。
- 验证所有非提交状态下 textarea 可编辑。

### Batch 2：环境拓扑与状态映射

- 添加 `.scene-container::before` 和 `::after` 环境层。
- 接入 Tone/App Status 独立变量及组合滤镜。
- 添加 `backdrop-filter` fallback 和 reduced-motion 规则。
- 通过实际浏览器属性切换、截图与像素差确认各状态可辨且前景清晰。
