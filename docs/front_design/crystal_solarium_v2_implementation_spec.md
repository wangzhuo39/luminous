# Luminous 晶格温室 v2 实施规格

> 实施状态：CV2-B1–B5 已完成并通过验收（2026-07-26）。证据见 `acceptance/crystal-solarium-v2/README.md`。

> 状态：三路 Gemini 多模态设计、CV2-B1–B5 分批实现与真实截图终审均已完成
> 更新时间：2026-07-26
> 作用域：全局主场景、空间入口、共享弹层物态、环境动态；不改变业务 API、状态机和安全适配器

## 1. 结论与完成度纠正

当前 `crystal_solarium_visual_rebase_v1.md` 完成的是 2.5D、光学 token、指针视差和共享磨砂材质的技术基线，不足以证明设计理念“晶格温室”已经完成。实际截图仍以人物设定图、平面蓝色网格、裸文字入口和左侧矩形面板为主，因此用户感知为“朴素”是准确反馈。

从本规格开始，完成度使用以下口径：

- v1：技术与材质基线，已完成；
- v2：空间构图、物件隐喻和数据驱动环境，已完成；
- 只有 v2 的桌面、移动、reduced-motion 截图与浏览器断言全部通过，才能称“晶格温室视觉完成”。

## 2. Gemini 设计来源

三次请求均为独立无状态调用。每次请求包含真实设计理念、现有 DOM/CSS/JS 行为、不可回归项和用户反馈，并附真实 Chromium 截图；没有要求模型读取本地路径。

| 设计面 | 结果 | 原始追踪目录 |
| --- | --- | --- |
| 主场景构图 | 主端点 attempt 1 成功，10,193 bytes | `/home/wz/gemini-api-traces/runs/20260726T044506.070610Z_luminous-crystal-v2-scene-design_0c8a3608/` |
| 空间物件与弹层 | 主端点 attempt 1 成功，14,277 bytes | `/home/wz/gemini-api-traces/runs/20260726T044506.071109Z_luminous-crystal-v2-objects-design_54bd85ea/` |
| 动态光影 | 主端点 attempt 1 成功，10,869 bytes | `/home/wz/gemini-api-traces/runs/20260726T044506.072570Z_luminous-crystal-v2-dynamics-design_33db06a2/` |

共享上下文、三个提示词、附图副本、请求 manifest、原始响应和端点元数据均保存在上述项目外目录。三个回答完整命中各自结束标记。

## 3. 设计主张：静谧的穹顶深谷

v2 只采用一个构图方向，不再并列多个主题：用户位于半透明温室内部，消失点在画面中央偏上；远景拱形光窗与左右立柱收束视线，中景伴侣与光束安静在场，前景浅水面承载对话、输入和信笺。

### 3.1 桌面镜头，1440×1000

- 相机近似 50mm 标准视角，`perspective: 1200px`，`perspective-origin: 50% 45%`；不使用夸张广角。
- 巨大拱形光窗位于人物后方，左右各三道纵向立柱向消失点收束。光窗是建筑，不再是铺满屏幕的横竖网格。
- 底部约 30% 为浅水面/玻璃地面，使用透视线和极弱反射引导深度；输入水面位于最前景。
- 人物宽度控制在视口的 30%–35%，默认约 450px。人物图作为可替换中景资产，脚部以线性雾化融入水面，不再使用黑色径向洞式遮罩。
- 对话位于人物下方偏左、水面上方，保留字幕感；不能恢复聊天气泡。
- Today 与 Memory 依附左侧建筑/水位线，Privacy 依附顶部雾帘边缘，Outbox 依附右下水面；入口必须有物理载体。

### 3.2 移动镜头，390×844

- 采用独立构图，而不是简单隐藏桌面装饰。`perspective-origin` 下移至 `50% 65%`，形成轻微仰视天窗。
- 人物占画面上部约 60%–65%，脚部更早淡出，为对话、入口和输入保留稳定暗部。
- UI 不使用动态 Z 位移，保证文字与触控区稳定；3D 只留在建筑和光效层。
- 四个入口沿输入上方“水位线”排列为有材质的微型物件 dock；不是普通导航条，也不能只显示裸文字。
- 虚拟键盘状态继续使用现有正常文档流与 sticky action，不用真实键盘动画换取视觉效果。

## 4. 七层空间结构

| 从远到近 | DOM/职责 | 建议空间 | 光学与运动 |
| --- | --- | --- | --- |
| 1 深层基底 | `.scene-background`，时间色温与暗部 | `translateZ(-1200px)` | normal；只做缓慢色温插值 |
| 2 拱形光窗 | 新增 `.solarium-vault` 内联 SVG | `translateZ(-760px)` | 细线冷白边缘，opacity 0.16–0.34；小视差 |
| 3 纵深立柱 | 新增 `.solarium-ribs` SVG group | 同光窗，独立横向位移 | 不动画 stroke/filter；以 opacity/transform 响应 |
| 4 水面/地面 | `.solarium-floor` | `rotateX(74deg) translateZ(-260px)` | soft-light/screen，避免 color-dodge 过曝 |
| 5 体积光与雾 | `.volumetric-rays`、新增 `.ambient-mist` | `translateZ(-140px)` | 静态 blur；只动画 transform/opacity |
| 6 伴侣主体 | `.companion-container` | `translateZ(0)` | 线性遮罩、边缘呼吸，不动画 filter |
| 7 晶体、入口与水面 UI | `.crystal-prisms`、`#portals-layer`、输入 | `80px` 到 `240px` | 前景视差最大；弹层打开时暂停 |

建筑 SVG 使用 `viewBox="0 0 1440 1000"`、`preserveAspectRatio="xMidYMid slice"` 和 `vector-effect="non-scaling-stroke"`。SVG 仅包含路径、渐变定义和装饰性 group，整体 `aria-hidden="true"`、`focusable="false"`，不引入 Canvas、WebGL 或大型依赖。

## 5. 全局光学 token

```css
--solarium-perspective: 1200px;
--solarium-origin-y: 45%;
--glass-edge-light: rgba(230, 249, 255, 0.28);
--glass-edge-shadow: rgba(1, 8, 14, 0.24);
--vault-line: rgba(220, 246, 251, 0.22);
--vault-line-faint: rgba(184, 225, 236, 0.10);
--window-core: rgba(225, 246, 250, 0.26);
--ray-warm: rgba(244, 222, 191, 0.16);
--ray-cool: rgba(178, 226, 240, 0.14);
--water-edge: rgba(216, 244, 249, 0.20);
--mist-color: rgba(181, 220, 232, 0.08);
--object-focus-ring: 0 0 0 2px rgba(224, 248, 252, 0.60), 0 0 24px rgba(164, 211, 229, 0.34);
```

旧 `.solarium-architecture` 的全屏横竖 `repeating-linear-gradient` 必须删除或降为局部远景刻度；人物径向黑洞遮罩替换为底部线性雾化；背景深黑仍可作为对比底，但不能形成大块死黑。

## 6. 空间物件系统

所有入口继续使用真实 `<button>`；不采纳“把 button 完全设为 opacity:0、视觉放在兄弟节点”的实现，因为那会破坏可见焦点与视觉点击目标的一致性。正确做法是让按钮自身成为物件容器，在按钮内部加入 `aria-hidden` 的形态层，并保留克制的可见标签。

### 6.1 通用语法

- `portal-object`：真实 button，拥有 48px 以上热区、空间定位和 focus-visible 光晕。
- `portal-object__shape`：`aria-hidden` 的 SVG/CSS 形态，不截获指针。
- `portal-object__label`：默认低对比，hover、focus 或触控设备时清晰出现。
- `is-unread`：只提升核心光的温度、亮度和低频呼吸，不显示红点；现有数字只可保留给辅助技术，视觉隐藏。
- `is-open`：形态从原位置淡出或成为弹层的视觉来源；焦点仍由既有 overlay controller 管理。

### 6.2 四个入口

- Today：左上/左中远景光窗的一段刻度光片，形态纵向、细长、与建筑立柱共线。
- Memory：左侧水位线附近的匿名晶簇，固定形态层与动态密度晶体区分；按钮标签是“记忆”。
- Privacy：右上方一段雾面帘拉环/结露边缘；打开时扩展为全屏雾帘。
- Outbox：右下水面上的折叠信笺；未读以纸芯暖光和缓慢呼吸表达，不暴露数字红点。

移动端四者吸附在输入上方水位线：Today 光片、Memory 水下晶光、Privacy 霜片、Outbox 折叠信笺。形态不同但尺寸、标签和 focus 规则一致。

### 6.3 弹层物态

继续保留原生 dialog、ESC、外围关闭、焦点陷阱和焦点恢复。通过 `data-space` 赋予不同物态：

- Today：从远景光窗的窄光片扩展为连续生活切片；桌面偏左但宽度和纵深更大，不能是封闭卡片。内部资源切换只改变内容折射方向，不重复播放整个入场。
- Memory：使用不规则晶体外轮廓和多个静态切面装饰，但可访问内容仍保持可滚动的线性阅读顺序；不采纳难以键盘/屏幕阅读器操作的 3D 旋转轮播。
- Outbox：近景悬浮信笺，低反射暖白纸面，位置靠近水面；保留长文本可读性和关闭按钮语义。
- Privacy：近全屏无闭合边框的霜化雾帘，压低中远景并暂停视差；设置项仍是正常表单。
- Diary：Today 连续光片中的低反射沉积纸，不再增加卡片边界；正文滚动上下使用 mask 渐隐，但键盘聚焦元素不得被遮住。

## 7. 环境动态契约

### 7.1 安全输入

环境模块只接收安全、有限的派生值：

```text
local Date / local hour
tone: calm | warm | quiet | concerned | unknown
activityPresence: active | paused | none
memoryCount: 非负整数；不可获得时为 0/unknown
outboxUnread: boolean
dnd: boolean
activeSpace: today | memory | outbox | privacy | null
reducedMotion: boolean
coarsePointer: boolean
documentVisible: boolean
```

Memory 装饰只能使用数量分桶，任何 memory key、title、text 或 evidence 都不能进入装饰 DOM、dataset、style 或日志。

### 7.2 派生变量

| CSS 变量 | 范围 | 唯一消费者 |
| --- | --- | --- |
| `--solar-phase` | 0..1 | 背景时间色温插值 |
| `--light-angle` | -60deg..60deg | 体积光 transform/渐变角度 |
| `--ray-focus` | 0.72..1.22 | 光束静态 blur 档与 opacity；不逐帧动画 filter |
| `--mist-density` | 0..1 | 雾层 opacity；DND/Privacy 提升 |
| `--breath-period` | 6s..12s | 人物边缘与光束伪元素的低频 opacity |
| `--crystal-density` | 0..1 | 匿名晶体 opacity/scale |
| `--presence-lift` | 0..1 | active/paused 的水面边缘亮度 |
| `--letter-warmth` | 0..1 | Outbox 信笺纸芯光 |

时间基底使用 dawn 05:00–08:00、day 08:00–17:00、dusk 17:00–19:00、night 19:00–05:00 四段连续插值。tone 只叠加光束聚拢、呼吸周期和小幅暖冷偏移，不再通过 4×5 个硬编码主题覆盖时间。

### 7.3 匿名晶体密度

- 0：保留入口晶簇载体，但动态记忆晶体为 0；
- 1–3：2–3 个匿名节点；
- 4–8：5–7 个匿名节点；
- 9+：最多 12 个匿名节点；
- 只有跨越分桶时才增删 DOM；位置来自固定 seed 表，不使用随机数造成截图漂移。

### 7.4 运动优先级

1. 空间打开/关闭最高：背景后推、雾密度提升、物件进入；600ms、`cubic-bezier(.2,.8,.2,1)`。
2. 指针视差中等：沿用 lerp 0.08；任何 dialog 打开时暂停并回中。
3. 空闲呼吸最低：仅 opacity，6–12s；不与入场同时抢夺 transform。

`prefers-reduced-motion` 下禁用 Z 轴飞入、视差和呼吸，只保留不超过 150ms 的 opacity 状态变化。粗指针禁用指针监听。页面隐藏时 rAF 和 CSS 动画均暂停。性能降级不使用 `hardwareConcurrency` 猜测；优先依赖 `@supports`、reduced-motion 和明确的 `data-effects` 策略。

## 8. JS 模块边界

新增模块建议：

```text
js/scene-environment.js
  deriveSolarState(date)
  deriveEnvironment(input)
  applyEnvironment(scene, environment)
  createMemoryCrystals(container, bucket)
  initSceneEnvironment(options) -> { update(), destroy() }

js/scene-parallax.js
  继续只负责指针输入和逐帧 transform
  新增 setSuspended(boolean)，不读取 AppState/API
```

`main.js` 只把安全 ViewModel/AppState 摘要传给环境模块，并根据当前 dialog 同步 activeSpace。环境模块不调用 API、不读取服务端原始对象、不持久化数据。

## 9. 实施批次

### CV2-B1：建筑与镜头重构

- 增加拱形光窗/立柱 SVG、雾层、水面焦散层；
- 调整人物取景和线性遮罩；
- 删除平面网格主导感；
- 独立桌面与移动构图；
- 保持现有入口和弹层行为不变；
- 先用静态 fixture 截图证明主场景空间成立。

### CV2-B2：空间入口物件化

- 重构四个 portal button 内部装饰；
- visual unread 改为信笺纸芯光；
- 增加 focus、hover、open、移动水位线 dock；
- 不改 overlay controller 的事件和语义。

### CV2-B3：差异化弹层物态

- Today 光窗、Memory 晶体、Outbox 信笺、Privacy 雾帘；
- Diary 连续沉积纸；
- 保留所有 loading/empty/error/form/keyboard 状态。

### CV2-B4：环境动态

- 本地时间相位、tone、activity、Outbox unread、DND 和 activeSpace 驱动；
- 若当前 Memory API 尚未提供安全数量，则先保持 unknown/0，不伪造数据；接入时只传 count；
- 固定 seed 匿名晶体；
- 视差暂停/恢复、visibility 和 reduced-motion 降级。

### CV2-B5：浏览器验收与 Gemini 终审

- 桌面 dawn/day/night、移动、reduced-motion、粗指针、Today/Memory/Outbox/Privacy、长 Diary、键盘；
- 检查无横向溢出、无 console/pageerror、焦点恢复和安全 DOM；
- 把最终截图发送给 Gemini 多模态终审；只修 P0/P1 后更新视觉基线状态。

## 10. 验收标准

1. 首屏没有裸露的纯文字入口；四个入口均有可辨识且不同的物理载体。
2. 静态截图中可分辨拱形光窗、收束立柱、水面/地面、人物中景和前景物件至少五个空间层次。
3. 人物不再像铺满视口的海报；桌面宽度不超过建议占比，脚部自然融入水面。
4. 光窗不是铺满屏幕的规则横竖网格；建筑线条沿消失点收束。
5. Today 打开时是光窗接近而非普通矩形卡片凭空出现；Memory、Outbox、Privacy 三者外观不能同构。
6. 未读不用红点或可见数字角标，使用信笺纸芯的低频光。
7. 时间和 tone 能独立改变色温与光束聚拢；切换无硬跳。
8. 任何 dialog 打开时视差暂停并回中，远/中景出现焦距隔离。
9. reduced-motion 下无非必要 Z 轴/呼吸/视差运动，但空间层级在静态画面中仍成立。
10. 390×844 无横向溢出、入口热区至少 44px、输入与虚拟键盘状态可用。
11. 装饰 DOM 全部 `aria-hidden`，不包含任何内部 key、Memory 文本或服务端原始错误。
12. 高频动画只更新 transform/opacity；匿名装饰节点总数不超过 20，rAF 在稳定、后台或弹层打开时休眠。

## 11. 明确不采用的 Gemini 建议

- 不使用 Canvas/WebGL/Three.js；内联 SVG 足以解决建筑线条抗锯齿和响应式问题。
- 不把真实 button 完全透明化并把视觉放到兄弟节点；焦点与视觉载体必须一致。
- 不做 Memory 3D 自动旋转轮播；保留线性可访问阅读，外层用晶体切面表达。
- 不逐帧动画 blur、filter 或 box-shadow；这些属性只随低频状态切换。
- 不用 `hardwareConcurrency` 自动判定低端设备；避免不稳定分支和不可复现截图。
- 不强制使用 `color-dodge`；以 screen/soft-light 保持克制并降低跨屏幕过曝风险。

## 12. 2026-07-26 实施与审核结论

- CV2-B1–B3 已落入 `index.html` 与 `styles/crystal-solarium.css`：穹顶、七层空间、四个实体入口和四种弹层物态均已实现。
- CV2-B4 已落入 `js/scene-environment.js`；`main.js` 只传有限安全摘要，`scene-parallax.js` 增加可销毁的暂停接口。S4 接入前 `memoryCount=0`、`dnd=false` 是明确的 unknown fallback，不是假数据。
- 环境模块使用固定 seed，匿名晶体最多 12 个，不接收正文或 key；6 个专项 Node tests 覆盖时段边界、有限枚举、恶意输入降级、密度上限、CSS 变量和 timer 清理。
- CV2-B5 通过 3 场景、8 张截图浏览器验收；晨夜背景、夜间人物亮度、移动入口错落、隐私居中与视差暂停均有机器断言。
- Gemini 第一轮按真实截图给出 50/100，修正 P0/P1 后复审为整体 86、桌面 88、移动 84、隐私 85，并明确“无 P0”“晶格温室已实现”。
- 权威证据与有效 trace 路径统一记录在 `acceptance/crystal-solarium-v2/README.md`。
