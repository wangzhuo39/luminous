# Luminous 晶格温室视觉重构 v1

> 状态：已实现并通过本地浏览器验收（2026-07-26）
> 作用域：全局主场景、共享弹层材质、Today/Task/Routine 内容视觉；不改变业务行为和接口契约

## 1. 为什么需要重构

此前 S1–S3 已建立可靠的交互、状态、接口和验收骨架，但视觉实现只使用了冷蓝色、单张人物背景、全屏模糊和深色矩形 dialog。它满足“可用”，却没有兑现设计规范中的主推概念“晶格温室”：

| 设计要求 | 重构前事实 | 判定 |
| --- | --- | --- |
| 纵深光窗 | 单色背景与人物设定图 | 缺失 |
| 晶格建筑 | 无专用 DOM/CSS 图层 | 缺失 |
| 物理折射 | 仅 `backdrop-filter` | 不足 |
| 远/中/前景视差 | 无 `perspective` 和视差运行时 | 缺失 |
| 人物在场 | 人物图铺满视口，像海报 | 不符合 |
| 凝露输入 | 普通圆角半透明输入框 | 不足 |
| 生活切片材质 | 近黑矩形 dialog + 彩色顶边 | 不符合 |

因此 B4 的行为验收仍然有效，但旧视觉验收不能代表设计规范已完成。本次重构把“晶格温室”升级为后续 B5–S5 必须继承的全局视觉基线。

## 2. Gemini 与 Codex 的分工

Gemini 是无历史、不能读本地文件的多模态 API，不是 code agent。本轮把任务拆成两个可并发的独立设计请求：

1. 场景世界：镜头、DOM 图层、token、光窗/晶格/折射配方、响应式和视差契约；
2. 内容材质：Life Slice、Memory Crystal、Letter、Privacy Gauze，dialog、表单、动作和移动端材质片。

每次请求直接附带完整设计文档、真实 HTML/CSS 和截图。Codex 负责选择输出、纠正层叠上下文、编写视差 JS、集成业务 DOM、运行测试和根据 Chromium 截图调参。最后由 Gemini 对最终截图进行独立多模态复审。

## 3. 最终空间结构

```text
scene-background                深空色温
solarium-architecture           纵深光窗、穹顶晶格
volumetric-rays                 丁达尔光束与晨曦折射
solarium-floor                  透视玻璃地面/水面
companion-container             中景人物，CSS 裁切与渐隐
crystal-prisms                  前景折射晶体
dialogue-stream                 独立字幕深度与暗部保护
input-surface-container         凝露水面输入
portals-layer                   情境化空间入口
overlay-manager / dialog        不参与视差的边界层
```

装饰层统一放在 `.solarium-environment[aria-hidden="true"]`，不进入可访问树、不接收指针事件。原有 `id`、`data-hook`、dialog 语义和业务事件保持不变。

## 4. 代码归属

- `styles/tokens.css`：光学颜色、焦散、晶体/水面阴影、四类材质 token；
- `styles/crystal-solarium.css`：加载顺序最后，统一拥有全局艺术指导、场景图层、共享材质和响应式视觉覆盖；
- `styles/scene.css`、`overlays.css`、`life-flow.css`：继续拥有基础布局和 feature 行为样式，不在其中复制艺术指导数值；
- `js/scene-parallax.js`：只读取指针/可见性/减少动效偏好，只写装饰层 CSS 变量；不读取 AppState、不调用 API；
- `js/main.js`：只负责初始化与销毁视差模块；
- `index.html`：只增加静态、`aria-hidden` 的温室装饰 DOM。

将艺术指导放在独立末级样式表是有意的稳定化策略：当前阶段允许快速调校一个完整概念，避免把同一材质散落到各 feature。后续只有在视觉基线稳定且重复覆盖成为维护成本时，才把规则回收至原样式表。

## 5. 视觉不变量

后续新增 Activity、Diary、Reminder、Calendar、Action 光签时必须遵守：

1. 不得删除光窗、体积光、晶体阴影和凝露输入，或降级为单张背景图。
2. 不得恢复近黑实心 dialog、彩色顶部条、卡片墙、实心红色危险按钮。
3. Life Flow 内容是同一块连续生活切片，层级来自字距、留白、时间刻度和微光，不靠嵌套卡片。
4. 新输入继承凝露式底边状态：默认、hover、focus、filled、disabled、invalid。
5. 桌面可以有轻微指针视差；粗指针、移动端、页面隐藏和 reduced-motion 必须静止。
6. 环境 tone/status 仍由现有安全 CSS 变量驱动，不增加技术状态面板。
7. 所有正文、焦点环和 44px 触控热区优先于光学效果。

## 6. 响应式镜头

- 1440×1000：广角温室，人物居中略偏右，左右晶体形成前景，Today 在左侧垂直居中展开。
- 1280×720：透视缩至 `900px`，人物适度放大，Today 宽 380px、最大 85dvh。
- 390×844：透视缩至 `600px`，光窗收束成顶部天窗，隐藏次要晶体，人物使用独立裁切；输入和 dialog 退化为贴底 2D 材质片。
- 虚拟键盘：Today 最大 48dvh，动作区 sticky；不依赖真实键盘动画完成布局。

## 7. 多模态复审与问题处理

Gemini 最终审查结论为“有条件通过”，概念兑现度 9/10：明确认为页面已经从普通冷色玻璃跨越为具有物理光学逻辑的实体空间。它发现移动端人物背景缺少 `background-repeat: no-repeat`，产生重复人脸（P0），同时丢失底部渐隐（P1）。Codex 随后：

- 为所有人物背景显式禁止 repeat；
- 移动端恢复独立底部渐隐；
- 提高移动表单对比度；
- 为字幕增加低强度暗部保护；
- 重新生成截图并通过全部专项断言。

这次处理说明：多模态审查必须看真实截图；仅检查 computed style 无法发现背景平铺这样的视觉事故。

## 8. Gemini 请求记录

所有输入、上下文、图片、原始响应、重试和端点信息位于项目外：

- 场景世界（选用 attempt 002）：`/home/wz/gemini-api-traces/20260726T032309.478878Z_luminous-crystal-scene-world-v1_ff51a083/`
- 内容材质（首轮成功）：`/home/wz/gemini-api-traces/20260726T032309.478013Z_luminous-crystal-material-ui-v1_474d27cb/`
- 最终多模态复审（备用端点 attempt 2 成功）：`/home/wz/gemini-api-traces/20260726T034135.328078Z_luminous-crystal-visual-audit-v1_b4d68487/`

场景请求的三个回答均完整，但模型把结束标记包在反引号中，严格裸后缀校验误判并触发重试；详见该 trace 的 `SELECTION_NOTE.md`。

## 9. 验收基线

机器与截图证据见 `acceptance/crystal-solarium-visual-rebase-v1/README.md`。当前结论：

- Node 全量：136/136；
- B3 浏览器：2 个视口、2 个场景、6 张截图；
- B4 浏览器：3 个场景、6 张截图；
- 晶格温室专项：桌面、移动、reduced-motion 3 个场景、4 张截图；
- 产品 JS 语法和 `git diff --check` 通过。

## 10. 已知边界

当前人物素材本身是角色设定稿，不是透明立绘。CSS 已通过容器裁切、多层渐变和径向遮罩消除标题、分镜和表情条，但未来若获得正式透明人物素材，应只替换 `.companion-container` 的资源和取景参数，不能删除温室 DOM、光学层或视差契约。
