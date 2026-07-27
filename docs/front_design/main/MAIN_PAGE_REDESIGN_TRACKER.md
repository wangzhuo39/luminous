# 主页面 UI 复原追踪

> 目标：以 `ui.png` 为视觉基准，使用 `yezheng.png` 作为人物/背景素材，逐轮复原 Luminous 主页面，并通过 Gemini 多模态审查与 Playwright + Chromium 验收。

## 目标素材

- 目标截图：`ui.png`（941 × 1672）
- 人物背景图：`yezheng.png`（941 × 1672）
- 当前页面入口：`apps/companion-web/companion-ui/index.html`
- 当前页面编排：`apps/companion-web/companion-ui/js/main.js`
- 架构约束：`docs/front_design/main/FRONTEND_ARCHITECTURE.md`
- UI 实现参考：`docs/front_design/main/ui实现.md`

## 当前进度

### 2026-07-27 · Baseline 0

- 已确认项目为原生 HTML/CSS/ES Modules，默认 API 模式，`?mode=fixture` 可离线复原。
- 已启动本地 mock 服务：`http://127.0.0.1:8000/?mode=fixture`。
- 已使用 Playwright 1.62.0 + Chromium 1234 生成基线截图：
  - `/tmp/luminous-current-941x1672.png`
  - `/tmp/luminous-current-390x844.png`
- 基线无 console error，但与 `ui.png` 差距明显：当前仍是暗青色晶格温室构图，人物缩小且偏上，缺少目标中的顶部信息、四个圆形入口、连续大字号对白、三项状态面板和底部水面输入区。
- Playwright MCP 当前配置指向系统 Chrome，而系统未安装 `/opt/google/chrome/chrome`；已改用项目缓存中的 Chromium 可执行文件完成本地脚本验收。

### 2026-07-27 · Architecture pass 1

- `index.html` 的主场景顶部信息和状态面板移入 `js/features/main-scene/main-scene-shell.js`，避免入口文件继续堆叠静态模板。
- `main.js` 的 DOM 查询移入 `js/dom-registry.js`，对白/场景渲染移入 `js/features/main-scene/main-scene-view.js`。
- `app-state.js` 保留兼容 facade；实现拆到 `js/state/app-store.js`、`core-state.js`、`life-flow-schema.js`、`life-flow-state.js`。
- 新增 `tests/frontend/architecture-boundaries.test.mjs`，对入口体量、状态 facade 和主场景样式分层建立护栏。
- 主场景样式从单一 `main-reconstruction.css` 拆为 `styles/features/main-scene/` 下的 surface 文件，并由 `styles/main-scene.css` 统一加载。
- 结构回归：前端 `175/175` 测试通过；Chromium 桌面/移动截图无 console error、无失败资源请求。
- 视觉微调：将桌面 portal 组从边缘 2.5% 收回到 5% 安全区，保留移动端独立位置规则；当前 acceptance 脚本输出 `/tmp/luminous-main-page-941x1672.png` 与 `/tmp/luminous-main-page-390x844.png`。

### 2026-07-27 · Gemini iteration 2 / asset pass

- Gemini 明确指出剩余差异集中在 portal 水晶材质、发送按钮亮度、对白星芒 rail、状态框节点和输入文案。
- 依据 `ui实现.md` 将入口图标和状态图标移为独立 SVG，并新增 `assets/frames/status-*.svg` 三段式状态框架；HTML 文字仍保持动态可更新。
- 状态框改为固定两端装饰 + 可伸缩中段 + 中央晶体，portal 使用多层轨道/发光图标，发送按钮改为实心发光纸飞机。
- 最新 Gemini trace：`/home/wz/gemini-api-traces/runs/20260726T172839.732160Z_luminous-main-iteration-2-audit-v1_f6594cc3`。

### 2026-07-27 · Painted artwork pass

- 接受“复杂装饰需要先准备美术资产”的实现约束，不再用 CSS 继续临摹状态栏、输入框和发送按钮的全部细节。
- 以 `ui.png` 为视觉语言参考，通过内置图像生成工具制作并透明化三项独立 PNG：
  - `assets/generated/status-frame-ornate.png`
  - `assets/generated/input-frame-glass.png`
  - `assets/generated/send-button-crystal.png`
- 状态栏文字、状态值、交互和无障碍语义仍由 HTML 提供；PNG 只承担玻璃、晶体、星轨和花纹层。原三段式 SVG 框架保留在图片下方作为加载降级。
- 输入框文案仍由 `<textarea>` 动态渲染，装饰图不包含文字；纸飞机的等待/重试状态仍沿用独立 DOM 状态层。
- 素材生成方式、尺寸和 prompt 意图记录在 `apps/companion-web/companion-ui/assets/generated/README.md`。
- 验收：前端测试 `178/178` 通过；Playwright + Chromium 桌面/移动视觉验收 `2/2` 通过，无 console error、失败资源请求或横向溢出。

## 迭代记录

| 轮次 | 输入/来源 | 主要动作 | 验收证据 | 状态 |
| --- | --- | --- | --- | --- |
| 0 | `ui.png`、当前页面截图 | 建立视觉与运行基线 | Playwright 截图、console error 检查 | 已完成 |
| 1 | Gemini 多模态审查、结构盘点 | 主场景重建与前端边界拆分 | Chromium 截图、175 项测试、架构护栏 | 已完成 |
| 2 | `ui实现.md`、独立美术资产 | 接入状态栏、输入框和发送按钮透明 PNG，保留动态内容层 | 178 项测试、桌面/移动 Chromium 截图 | 已完成 |

## 目标验收清单

- [x] 941 × 1672 目标构图与素材裁切基本一致
- [x] 顶部时间、天气文案、叶筝身份和更多按钮位置/层级一致
- [x] 左右四个圆形悬浮入口与文字标签完成（装饰纹理仍可继续精修）
- [x] 人物面部、发饰、手势和主体比例与目标一致
- [x] 对话区呈现连续文本流，不回退为聊天气泡
- [x] 三项状态面板与水晶玻璃边框完成
- [x] 底部输入区、发送按钮和水面质感完成
- [x] 390 × 844 移动布局可用，人物/文本/输入区不溢出
- [x] reduced-motion、键盘弹起、fixture 模式不破坏；API 模式需接入环境再验收
- [x] Playwright/Chromium 无 console error、无失败资源请求

## Gemini 轮次

Gemini 请求、响应和图片副本保存在 `/home/wz/gemini-api-traces/runs/`，本文件只记录摘要和采用的改动，不记录任何密钥。

| 轮次 | 请求标签 | 结论 | 采用内容 |
| --- | --- | --- | --- |
| 1 | `luminous-main-baseline-audit-v1` | 目标几何：顶部 header、左右 portal、对白 rail、status strip、composer；隐藏旧温室层 | `/home/wz/gemini-api-traces/runs/20260726T164747.588519Z_luminous-main-baseline-audit-v1_2a46fd0e` |
| 2 | `luminous-main-iteration-1-audit-v1`（primary/backup） | 已提交目标图与 Chromium 当前截图；外部服务本轮未返回可解析正文，trace 保留用于排查 | `/home/wz/gemini-api-traces/runs/20260726T170814.297288Z_luminous-main-iteration-1-audit-v1_8e0a91d9`、`/home/wz/gemini-api-traces/runs/20260726T171633.251891Z_luminous-main-iteration-1-audit-v1-backup_306b583d` |
| 3 | `luminous-main-iteration-2-audit-v1` | P0/P1：独立 SVG 图标、三段式状态框、发送按钮发光、对白 rail 星芒、移动最小字号 | `/home/wz/gemini-api-traces/runs/20260726T172839.732160Z_luminous-main-iteration-2-audit-v1_f6594cc3` |
| 4 | `luminous-main-iteration-3-final-audit-v1` | P1 集中在花纹与晶体材质；据此转入独立透明 PNG 美术资产，而非继续增加 CSS 复杂度 | `/home/wz/gemini-api-traces/runs/20260726T174328.287246Z_luminous-main-iteration-3-final-audit-v1_90015cd1` |
