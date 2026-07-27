# Companion UI 前端结构约束

## 当前边界

主页面采用原生 HTML、CSS 与 ES Modules，不引入构建期组件框架。页面启动由 `main.js` 编排，但具体职责按以下边界分层：

视觉资产和装饰实现以 [`ui实现.md`](./ui实现.md) 为参考：动态文字保留 HTML，轻量入口/状态图标使用独立 SVG；复杂玻璃、晶体和花纹改用 `assets/generated/` 下的透明 PNG。三段式 SVG/CSS 框架保留为加载降级，避免把美术细节重新堆回样式代码。

| 层 | 目录/入口 | 只负责什么 |
| --- | --- | --- |
| 启动编排 | `js/main.js` | 组装依赖、注册控制器、触发 render，不承载大段 HTML 或状态迁移 |
| DOM registry | `js/dom-registry.js` | 集中查询稳定的 `data-hook` / id，业务模块不重复扫描 DOM |
| 主场景 feature | `js/features/main-scene/` | 主场景静态 chrome、对白渲染和视觉挂载 |
| 状态 facade | `js/app-state.js` | 保持历史导入 API 的薄兼容层 |
| 状态实现 | `js/state/` | store、会话状态、life-flow 状态和净化/校验纯函数 |
| 业务 feature | `js/features/*/` | controller、view、feature-specific state |
| 样式 feature | `styles/features/main-scene/` | 按 header、portal、dialogue、status、composer、responsive 拆分 |
| 美术资产 | `assets/icons/`、`assets/frames/`、`assets/generated/` | 独立图标、降级框架，以及状态栏/输入框/发送按钮的透明绘制层 |

## 不变量

- `app-state.js` 不允许出现 DOM 查询、事件监听或业务视图 HTML；新状态操作进入对应 `js/state/` 或 feature state。
- `main.js` 不新增静态 SVG/HTML 模板；新增页面表面放到 `js/features/<feature>/`。
- UI 组件只消费 view model，不把 API 原始响应或不安全字段写回页面。
- feature 之间通过 facade、controller 回调或明确的 view model 交互，禁止跨 feature 直接修改另一个 feature 的内部状态。
- 样式按页面表面拆文件；超过约 250 行的单文件需要说明原因或继续按职责拆分。
- 修改结构后必须运行 `npm test`，并用 Chromium 验证桌面 941 × 1672 与移动 390 × 844。

## 尺寸护栏

这些是维护阈值，不是为了压缩可读性而设置的硬性代码风格：

- `index.html` ≤ 620 行；只保留稳定 shell 和 overlay 语义结构。
- `main.js` ≤ 520 行；超过阈值优先抽取 view/controller，而不是继续追加函数。
- `app-state.js` ≤ 80 行；只允许 facade/re-export。
- 单个主场景 feature JS/CSS 文件 ≤ 300 行；复杂 surface 拆成同目录文件。

## 后续迁移

1. 将 `life-flow-controller.js` 的资源事件绑定按 today/resource/action 三类继续拆分。
2. 将 `crystal-solarium.css`、`life-flow.css` 的历史样式按 feature 入口拆分，并清理已被主场景覆盖的旧规则。
3. 为主场景增加稳定的浏览器视觉 acceptance 脚本，保留 console/network error、关键矩形和无水平溢出的断言。
