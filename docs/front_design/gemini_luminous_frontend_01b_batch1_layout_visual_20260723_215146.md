# Batch 1B：晶格温室的主界面布局、镜头语言与视觉系统

本规范承接 Batch 1A 的信息架构，旨在将“安静在场”的陪伴感具象化为可执行的布局与视觉参数。所有设计均基于 **Vanilla HTML/CSS/JS** 架构，利用 CSS 变量驱动状态切换。

---

## 1. DOM 与视觉图层规范

### 1.1 图层总览 (Z-index Hierarchy)
所有元素通过 `z-index` 在视口内构建 2.5D 的纵深感：

| 图层 ID | Z-index | 说明 | Pointer-events |
| :--- | :--- | :--- | :--- |
| `audit-layer` | 9999 | **基石层**：Trace/Ledger 深层审计，全屏覆盖。 | `auto` (隐藏时 `none`) |
| `sheet-layer` | 2000 | **边界层**：Settings/DND 雾面帘，自顶向下覆盖。 | `auto` |
| `overlay-layer` | 1000 | **浮层层**：Memory 晶体展开、Diary 详情。 | `auto` |
| `diegetic-portals` | 500 | **物件层**：悬浮晶体、未读信笺、时间刻度。 | `auto` |
| `air-input` | 400 | **前景层**：水面输入区，位于屏幕中下部。 | `auto` |
| `subtitle-dialogue` | 300 | **中景层**：AI 回复文本、角色动作描写。 | `none` (穿透) |
| `presence-halo` | 200 | **主体光晕**：伴侣背后的呼吸光影。 | `none` |
| `companion-figure` | 150 | **主体层**：伴侣立绘或未来 Live2D 容器。 | `none` |
| `environment-fx` | 100 | **环境特效**：雾气、流光、雨滴、尘埃。 | `none` |
| `background` | 0 | **远景层**：光窗、天空色温底色。 | `none` |

### 1.2 首屏不工具化规则
- **移除显性 Header/Footer**：没有任何固定的导航条。
- **隐藏 Scrollbar**：全局 `overflow: hidden`，仅在特定的 Overlay 内部允许局部平滑滚动。
- **动态入口**：Memory 和 Settings 默认透明度为 0，仅在鼠标靠近边缘或特定手势时显影。

### 1.3 状态驱动图层
通过在 `<body>` 或 `#app-root` 切换 class（如 `.is-thinking`, `.is-memory-open`）来控制：
- **idle**: 伴侣微弱呼吸，环境光线随时间流逝。
- **listening**: `air-input` 扩圈，`presence-halo` 频率加快。
- **replying**: `subtitle-dialogue` 逐字浮现，伴侣立绘伴随轻微 Z 轴推近。
- **dnd**: 全局覆盖 `.sheet-layer` (模糊度 20px)，色温转冷。

---

## 2. 桌面布局 1440x900 (Desktop)

### 2.1 区域比例与焦点
- **人物主体**：居中偏右，底部通过 `mask-image` 渐变消失在水面。
- **字幕区**：位于人物胸部下方（Y: 65%），宽度不超过 600px。
- **输入区**：位于屏幕底端向上 80px 处，横向居中。

### 2.2 ASCII Wireframe
```text
___________________________________________________________
| [Settings Pull-down Tab - Invisible]                    |
|                                                         |
|    (Memory Crystals)           /~~~~~~~~~\              |
|          *                    /           \             |
|         * *                  |  Companion  |            |
|          *                   |   (Subject) |            |
|                               \           /             |
|                                \_________/              |
|                                     |                   |
|          [Subtitle: The light feels warm today...]      |
|                                                         |
|          [Input: Touch the water surface...] (Letter)   |
|_________________________________________________________|
```

---

## 3. 笔记本布局 1280x720 (Laptop)

- **人物裁切**：由全身/大腿处裁切改为腰部裁切，上移人物重心。
- **字幕压缩**：行高由 1.8 缩减至 1.6，防止遮挡输入区。
- **入口收纳**：左侧晶体由散落状改为垂直排布。

---

## 4. 移动端布局 390x844 (Mobile)

### 4.1 核心策略
- **竖屏沉浸**：人物占满全屏背景，面部避开顶部 Notch。
- **键盘适配**：当 `input:focus` 时，人物向上平移 20%，字幕区淡出，为键盘留出空间。
- **手势交互**：
  - 从顶部下滑：拉出雾面帘（Settings）。
  - 长按底部：进入下潜模式（Trace）。

### 4.2 ASCII Wireframe
```text
__________________
| [ Settings ]   |
|                |
|      (O)       |
|    Companion   |
|      Face      |
|                |
|  [ Subtitle ]  |
|                |
|  [ Crystal ]   |
|  [  Input  ]   |
|________________|
```

---

## 5. 镜头语言与场景状态 (Cinematography)

| 状态 | 镜头 (Camera) | 人物缩放 | 环境光影 | 动效节奏 |
| :--- | :--- | :--- | :--- | :--- |
| **Idle** | 远景 | 1.0x | 慢速呼吸 (6s) | 静止，微弱粒子浮动 |
| **Listening** | 中景推近 | 1.05x | 光晕向中心汇聚 | 输入框呼吸频率加快 |
| **Replying** | 微震/推近 | 1.02x | 随文字节奏闪烁 | 文字逐字浮现 (Fade-in + Slide-up) |
| **Memory Open**| 后退/模糊 | 0.9x | 环境暗化 40% | 晶体由边缘飞入中心 |
| **DND Mode** | 极远景 | 0.8x | 覆盖半透明磨砂 | 所有的动作进入极慢速 |
| **Risk/Error** | 静止 | 1.0x | 边缘泛起冷白/微红 | 光影停滞，出现断裂质感 |

---

## 6. 视觉 Token 与 CSS 变量草案

```css
:root {
  /* 基础材质 */
  --luminous-bg: #0a0c10;
  --luminous-frost: rgba(255, 255, 255, 0.05);
  --luminous-glass: rgba(255, 255, 255, 0.1);
  --luminous-blur: blur(15px);

  /* 光影色调 */
  --color-moonlight: #e0e6ed; /* 月光冷白 */
  --color-ice-blue: #a5c4d4;   /* 冰蓝 */
  --color-mist-gray: #78848d;  /* 雾灰 */
  --color-warm-hint: #f4e8d1;  /* 极淡暖色(Proactive) */
  --color-boundary: #3d4b59;   /* 边界线 */

  /* 文本 */
  --text-main: rgba(224, 230, 237, 0.95);
  --text-sub: rgba(224, 230, 237, 0.6);
  --text-action: rgba(165, 196, 212, 0.8); /* 动作描写用冰蓝 */

  /* 动画 */
  --ease-in-out-luminous: cubic-bezier(0.4, 0, 0.2, 1);
  --anim-breath: 6s infinite var(--ease-in-out-luminous);
  --anim-float: 3s infinite ease-in-out;

  /* 布局间距 */
  --space-edge: 40px;
  --input-width: 500px;
}
```

---

## 7. 字体、排版与字幕规范

### 7.1 字幕系统
- **字体**：优先使用系统无衬线（Inter, PingFang SC），严禁使用衬线体。
- **正文 (AI Reply)**：`font-size: 1.125rem; line-height: 1.8; letter-spacing: 0.05em;`
- **动作描写 (Role Action)**：使用 `*` 包裹，颜色设为 `--text-action`，字号略小 (0.95rem)。
- **思考折叠 (Role Thinking)**：表现为文本上方的微弱“气泡破裂”图标，点击后在原位展开淡灰色斜体字。

### 7.2 交互反馈
- **输入框**：无边框，仅有一条 1px 的半透明底线。Focus 时底线向两侧延伸并产生光晕。
- **超长文本**：禁止出现滚动条。采用“自动淡出旧句”机制，即始终只保留最近的 3-4 行，上方旧句随 Z 轴推移淡化消失。

---

## 8. 材质、光效与环境物件

- **晶体 (Crystals)**：使用 `clip-path` 构建几何切面，配合 `backdrop-filter` 和多重 `box-shadow` 模拟折射。
- **信笺 (Letters)**：折叠的 SVG 路径，具有极淡的扫光特效 (CSS linear-gradient animation)。
- **水面 (Water Surface)**：输入区底部的 `linear-gradient`，伴随鼠标移动产生微弱的 `filter: displacementMap` 涟漪感（Canvas 降级为 CSS 模糊圆点）。
- **雾面帘 (Gauze)**：全屏 `backdrop-filter: blur(30px) saturate(80%)`。

---

## 9. 人物主体图规范

- **融合策略**：
  - 人物图层必须使用 `mix-blend-mode: normal`。
  - 底部 20% 使用 `linear-gradient(to bottom, transparent, var(--luminous-bg))` 进行消隐。
- **占位策略**：
  - 当前阶段使用高分辨率 WebP 静态图。
  - 预留 `#companion-canvas` 容器，未来直接挂载 Live2D SDK。
- **泛化性**：
  - 环境色温由 API 返回的 `state.mood` 映射到 `--color-ice-blue` 的色相偏移值，确保不同角色能“染”上不同的环境氛围。

---

## 10. Batch 1B 自检清单

1. [ ] 是否移除了 `index.html` 中所有的 `border` 属性？
2. [ ] 是否使用了 `backdrop-filter` 实现所有的 Overlay 背景？
3. [ ] 输入框是否已降级为“水面隐喻”（无边框、底部光晕）？
4. [ ] 字幕区是否能正确区分“正文”与“动作描写”的视觉色调？
5. [ ] 移动端下，键盘弹出时人物是否进行了平滑的位移避让？
6. [ ] 所有的状态切换（如从 Idle 到 Thinking）是否有至少 500ms 的 CSS Transition 过渡？
7. [ ] 晶体入口是否使用了 `pointer-events: auto` 而字幕区使用了 `none`？
8. [ ] 页面是否在 1440px 和 390px 宽度下均无水平滚动条？
9. [ ] 所有的 CSS 变量是否都定义在 `:root` 中以便 JS 动态修改？
10. [ ] 顶部 Settings 拉环在非 Hover 状态下是否达到了“近乎隐形”的视觉克制？
11. [ ] 伴侣立绘的底部是否平滑融合进了背景，而不是生硬的切断？
12. [ ] 没有任何高饱和度的（#0000FF 等）纯色块出现？
