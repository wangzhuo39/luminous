# Luminous S1 全流程复盘与后续阶段执行手册

> 状态：持续维护（Living Document）
> 复盘阶段：S1「静态主场景垂直切片」
> 整理日期：2026-07-25
> 适用对象：后续前端设计、实现、审查与验收执行者

本文档记录 S1 从项目理解、设计收敛、Gemini 多轮调用、代码集成、失败恢复到浏览器验收的完整过程。它不是视觉规范或架构文档的替代品，而是后续 S2、S3 等阶段应复用的执行方法。

相关文档：

- `frontend_architecture_v1.md`：工程分层、接口适配与阶段规划；
- `FRONTEND_AGENT_HANDOFF.md`：产品边界、体验目标和前后端安全边界；
- `frontend_design_guidelines.md`：视觉与交互指导；
- `frontend_api_contract_v1.md`：后端接口事实；
- `acceptance/static-prototype-s1/README.md`：S1 最终验收结果与截图索引。

## 1. S1 的目标、结果与明确边界

S1 的目标不是做一个“看起来像完整产品”的假前端，而是交付一个真实可运行、可验证、能为后续 API 接入保留正确边界的静态垂直切片。

最终交付包括：

- 以 `companion.png` 为唯一人物主视觉资产的桌面和移动主场景；
- Fixture → Adapter → ViewModel → AppState → DOM 的展示数据链路；
- 中文 IME 安全输入、同步本地 fixture 回复与最多五条消息；
- Today、Outbox、Memory、Privacy 四个原生 `<dialog>` 静态空间；
- 移动键盘状态、safe area、焦点恢复、静默 live region 和 reduced-motion；
- 桌面 `1440×900`、移动 `390×844` 的浏览器截图与交互验收。

S1 明确不做：

- 不调用 `/api/*`，不使用 `fetch`、XHR 或 WebSocket；
- 不实现 CRUD、持久化、流式响应或真实模型请求；
- 不显示或解析 `role_thinking`、`role_action`、analysis、prompt、trace、jobs、export 等内部信息；
- 不伪造网络成功、模型思考、生成等待或服务端已读；
- 不为未来功能提前放入无法验证的 UI 和状态。

## 2. 人与模型的职责划分

本阶段采用“Gemini 负责设计与实现候选，Codex 负责工程闭环”的分工。

### 2.1 Gemini 的职责

- 在完整上下文下提出视觉方向、组件体系与实现候选；
- 以小批次返回完整文件或精确 CSS 修正；
- 在实现后接收真实截图，执行多模态视觉审核；
- 不直接决定候选是否可以进入仓库。

### 2.2 Codex 的职责

- 理解项目、后端契约、产品边界和当前代码；
- 为每次无状态 Gemini 请求重新构造完整上下文；
- 控制任务粒度、输出格式、文件清单和禁止项；
- 检查响应是否完整、是否越界、是否与当前源码兼容；
- 修正模型代码中的安全、架构、状态同步和可访问性问题；
- 运行语法、安全扫描和真实浏览器测试；
- 保存全部输入、输出、失败尝试和截图；
- 只在通过验收后宣布阶段完成。

核心原则：Gemini 返回的是候选实现，不是可直接信任的补丁；HTTP 200 也不是交付完成信号。

```text
权威文档与当前代码
        ↓
无状态设计调用（多轮）
        ↓
合规修订与契约锁定
        ↓
小批次实现调用
        ↓
完整性 → 安全 → 架构 → 语法审查
        ↓
真实浏览器行为与截图
        ↓
多模态视觉复核
        ↓
全量回归、验收文档与阶段交付
```

## 3. 上下文与权威优先级

Gemini API 每次调用都是独立、无历史状态的。因此，每轮请求都必须显式附带足以重建任务背景的上下文。

S1 实现阶段采用以下优先级：

1. 当前批次 prompt 中的目标、范围和禁止项；
2. 项目权威文档与当前已集成源码；
3. Round 4 修订版最终契约；
4. Round 2 组件、状态与响应式规范；
5. Round 1 视觉方向；
6. 早期模型候选或被截断的响应。

其中：

- Round 1 回答“看起来和感受起来是什么”；
- Round 2 回答“由哪些组件、状态和数据边界构成”；
- Round 4 回答“哪些方案最终允许实现”；
- Round 3 仅保留为问题来源和修订依据，不能作为实现权威。

后续阶段必须继续附带早期设计层，而不能只给最后一份契约。只给 Round 4 会丢失视觉理由和组件细节；只给 Round 1/2 又会重新引入已被纠正的错误。

## 4. API 调用与项目外留痕

### 4.1 主备配置

主接口使用：

- `GOOGLE_GEMINI_BASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

备用接口使用：

- `GOOGLE_GEMINI_BACKUP_BASE_URL`
- `GEMINI_API_BACKUP_KEY`
- `GEMINI_BACKUP_MODEL`

两者均按 OpenAI-compatible `POST /v1/chat/completions` 调用。实现前分别测试文本请求，并用实际参考图确认多模态能力。API 密钥和完整端点不会写入项目文档或响应正文。

### 4.2 调用器

项目外工具目录：`/home/wz/gemini-api-traces/`

- `run_gemini_logged.py`：文本请求；
- `run_gemini_multimodal_logged.py`：文本、多个上下文文件和多张图片；
- `campaigns/`：每轮人工编写的 prompt；
- `runs/`：每次调用生成的不可覆盖运行目录。

每个 run 至少保存：

- 最终合成请求和 prompt 来源；
- 上下文文件路径；
- 图片副本、顺序、字节数与 SHA-256；
- 每次尝试的端点角色、HTTP 状态、耗时、超时和解析错误；
- 原始响应、提取后的 assistant 文本和 stderr；
- 成功尝试编号与最终 manifest；
- 经脱敏的元数据。

主接口失败时，`auto` 模式按尝试次数在主备配置之间切换。失败尝试不会被覆盖，成功重试也不会抹去之前的错误。

## 5. 设计阶段全过程

### 5.1 Round 1：视觉与空间方向

目标是先确定唯一体验方向，不急于写代码。

主要结论：

- 唯一空间隐喻为“晶格温室（Crystal Solarium）”；
- 角色是第一视觉层级，对话第二，输入第三，功能入口保持外围低打扰；
- 放弃传统聊天气泡、控制台、卡片仪表盘和功能墙；
- 色彩以深空灰、冷白、冰蓝和少量暖光为主；
- 桌面与 `390×844` 同时设计；
- S1 采用原生 HTML/CSS/ES Modules，无运行时框架和构建链。

Round 1 提供视觉北极星，但不能单独指导状态和代码实现。

### 5.2 Round 2：组件、状态与响应式体系

目标是把视觉方向转成可实现结构。

产出覆盖：

- Scene、Conversation、Today、Outbox、Memory/Privacy 的职责；
- Fixture 和 ViewModel 初步形状；
- AppState、事件、焦点、Dialog 和 z-index 规则；
- desktop、laptop、mobile、keyboard-open 尺寸约束；
- token、排版、材质和 motion 规则。

Round 2 仍包含后来被否决的内容，例如 `thinking` 状态、计时器式假回复、打开来信即清零未读、动作/思考展示字段。这说明细化程度高并不等于符合安全和真实性边界。

### 5.3 Round 3：最终契约候选，但未通过审查

Round 3 尝试合并前两轮，但暴露了严重问题：

- 为内部思考和动作通道保留可见 UI；
- 状态模型无法准确表达 active space、draft 和展示态；
- 五个 S1 视图边界没有完整保留；
- 用 `thinking`、延迟回复等方式暗示不存在的模型请求；
- 对 glassmorphism 和 Dialog backdrop 的描述不够克制或不可直接实现。

处理方式不是局部默许，而是把 Round 3 标记为 superseded，专门发起合规修订轮。

### 5.4 Round 4：合规修订与最终实现契约

Round 4 明确纠正：

- 普通 UI 不得识别、解析、存储或展示内部字段；
- S1 本地发送只能同步呈现 fixture 最终回复，不能伪装远端生成；
- 必须保留 scene、conversation、today、outbox、memory/privacy 五类 ViewModel；
- AppState 使用结构化对象，包含 activeSpace、conversation 和 presentation；
- View 只消费稳定 ViewModel，不读取未来原始 API 字段；
- `<dialog>` 必须支持明确关闭、Escape 和焦点恢复；
- backdrop-filter 只在必要表面使用并提供降级；
- 零依赖是阶段性工程判断，不是环境限制。

自此形成实现上下文组合：项目文档 + 当前源码 + Round 1 + Round 2 + Round 4 + 本批次 prompt。

需要注意，Round 4 的正文仍残留过一次“延迟 fixture / waiting state”的批次建议，与它自己的静态真实性约束冲突。实际实现 prompt 将“不使用 timer、不出现 waiting/thinking、同步呈现 fixture final reply”再次锁定，并以更高优先级覆盖该残留建议。这进一步说明：修订轮也必须逐条审查，不能仅凭“corrected”标签视为完全正确。

## 6. 实现阶段全过程

实现没有要求 Gemini 一次生成整个 S1，而是按“一个批次可独立审查、输出文件数量受控”拆分。

### 6.1 Batch 1：主场景视觉基础

目标：建立语义 HTML、token、base 和 scene CSS，并使用参考图构建主场景。

主要文件：

- `index.html`
- `styles/tokens.css`
- `styles/base.css`
- `styles/scene.css`

集成要点：

- 使用 `companion.png` 作为场景人物背景；
- `mask-image` 只用于将人物融入底部环境，不增加装饰渐变；
- 建立主场景、对话、输入、外围入口和 Dialog 骨架；
- 保留原生语义元素和可访问名称。

### 6.2 Batch 2：Fixture、ViewModel 与 AppState

目标：先固定展示数据边界，再继续增加交互。

新增模块：

- `fixtures.js`
- `view-models.js`
- `fixture-adapter.js`
- `app-state.js`
- `main.js`

Gemini 候选中出现的问题：

- 使用 `innerHTML`；
- 使用随机 ID；
- 把未知 author 当作 assistant；
- 留下 console 占位逻辑。

集成时的修正：

- 全部改用 `createElement`、`textContent` 和 `replaceChildren`；
- ID 使用确定性 fallback；
- 未知 role 直接过滤，不升级为 assistant；
- Adapter 只做白名单字段转换；
- View 不直接读取 fixture。

### 6.3 Batch 3：本地对话闭环

目标：实现 IME、安全提交、同步 fixture 回复和场景状态变化。

行为要求：

- composition 期间 Enter 不提交；
- Enter 提交，Shift+Enter 换行；
- 空白输入禁用；
- 同步追加 user 与 assistant final reply；
- 不使用 timer、fake async、thinking 或 generating；
- 最多保留五条消息；
- 清空输入、恢复焦点、滚动到最新消息；
- 只由独立 live region 播报一次反馈。

第一次响应虽然 HTTP 成功，但在 `main.js` 中途结束，且缺少 `scene.css`，属于“成功但不可用”。没有拼接猜测内容，而是创建 Batch 3B：附带当前源码、上次截断响应和原始权威上下文，把输出缩窄到四个文件。

Batch 3B 在第六次尝试由备用端点成功。其代码又把本地回复文案硬编码在 `conversation.js`，违反 Fixture → Adapter → ViewModel 边界。最终将回复和发送后 scene presentation 放回 fixture，经 Adapter 后由 AppState 消费。

### 6.4 Batch 4：四个静态空间

目标：完成 Today、Outbox、Memory、Privacy 四个原生 Dialog。

约束：

- `activeSpace` 是唯一逻辑状态；
- 同时只能打开一个 Dialog；
- 显式按钮、Escape 和点击 Dialog 空白区域均可关闭；
- 关闭后恢复到原 portal；
- 打开 Outbox 不修改 fixture 未读数；
- Memory/Privacy 不出现假的 CRUD 和设置开关。

该响应的 JavaScript 和 HTML 完整，但 CSS 在文件中途截断。此外，候选的 Dialog 切换逻辑会让旧 Dialog 的 `close` 事件错误地清空新 activeSpace。

修正方式：

- 手工补齐并审查 overlay CSS；
- 使用 `WeakSet` 标记由状态同步触发的关闭，区分用户关闭与控制器关闭；
- 先关闭非目标 Dialog，再打开目标 Dialog；
- 保持 native Dialog 的焦点语义。

### 6.5 Batch 5：响应式、键盘、无障碍与 motion

目标：同时完成 desktop、mobile、keyboard-open 和 reduced-motion。

实现内容：

- `100vh` fallback + `100dvh`；
- safe-area 与移动端 44×44 触控目标；
- `visualViewport` 驱动 `presentation.isKeyboardVisible`；
- `matchMedia` 驱动 `presentation.isReducedMotion`；
- message history 不再是 live region，独立 status node 是唯一 polite announcement；
- Dialog 移动端 sheet 布局；
- reduced-motion 禁用非必要过渡。

集成时继续修正：

- 状态未变化时不重复 render；
- 避免 safe-area 计算产生负 margin；
- 对话区域设置滚动上限，保证最新消息和输入始终可用。

### 6.6 多模态视觉审核

首次真实截图暴露了纯代码检查无法发现的问题：

- 桌面裁切露出原始设定图左侧文字，角色面部顶部被截断；
- 移动端对话与 Outbox 入口距离过近；
- Outbox backdrop 过暗，切断主场景连续性。

最后一轮 Gemini 同时接收四张图片：原始人物图、桌面初始、移动初始、桌面 Outbox。该轮只允许返回视觉审核和精确 CSS selector，不允许扩展 HTML、JS、资产或功能。

修正后：

- 桌面人物改为 `background-size: 200%`、`background-position: 50% 0%`；
- 移动人物改为 `350%`、`50% 0%`；
- 移动对话右侧预留 Outbox 入口空间；
- 支持 blur 时降低 backdrop 不透明度。

第二轮截图确认桌面不再呈现设定图文字，角色面部完整，移动层级和 Overlay 关系符合设计目标。

## 7. 最终代码结构与运行时数据流

```text
companion-ui/
├── index.html
├── companion.png
├── styles/
│   ├── tokens.css
│   ├── base.css
│   ├── scene.css
│   ├── overlays.css
│   ├── responsive.css
│   └── motion.css
└── js/
    ├── fixtures.js
    ├── fixture-adapter.js
    ├── view-models.js
    ├── app-state.js
    ├── conversation.js
    ├── overlays.js
    ├── presentation.js
    └── main.js
```

数据流：

```text
fixtures.js
  ↓ 白名单转换
fixture-adapter.js
  ↓ 稳定展示模型
AppState
  ↓
conversation / overlays / presentation controllers
  ↓
main.js semantic DOM render
```

后续接入 API 时，应新增 API client 和 API adapter，复用现有 ViewModel 与 View。不要让现有 View 开始解析原始后端 response。

## 8. 审查与验收关卡

每个批次都必须依次通过以下关卡。

### Gate 1：响应完整性

- 请求的文件是否全部出现；
- 每个 code fence 是否闭合；
- 文件是否在中途停止；
- 是否包含未请求文件；
- 输出是否引用不存在的 API 或 selector。

### Gate 2：安全与范围

扫描：

- `innerHTML`；
- `fetch`、XHR、WebSocket；
- local/session storage；
- timer 和随机 ID；
- thinking/action/prompt/trace/job/export 等内部概念；
- 假异步、假已读、假网络成功；
- 未经许可的依赖。

### Gate 3：架构与状态

- Fixture 是否只由 Adapter 读取；
- View 是否只消费稳定 ViewModel；
- AppState 是否仍是唯一交互状态来源；
- controller 是否夹带展示数据；
- 未知角色和字段是否默认拒绝；
- Dialog、focus 和 activeSpace 是否可能不同步。

### Gate 4：静态验证

- 所有 JS 执行 `node --check`；
- HTML 引用文件全部存在；
- 禁止项扫描通过；
- 非 mask 场景不出现装饰渐变；
- 旧入口和旧截图不留在产品目录。

### Gate 5：真实浏览器行为

项目外脚本：`/home/wz/gemini-api-traces/browser-tools/verify-s1.mjs`

覆盖：

- 初始 fixture 渲染；
- 空白输入禁用；
- composition 期间 Enter 不提交；
- 本地发送、回复、tone、draft、focus；
- 五条消息上限；
- 四 Dialog 单实例打开、关闭和焦点恢复；
- Outbox 未读值不被伪改；
- 44px 触控目标；
- reduced-motion；
- 控制台错误与外部/API 请求。

### Gate 6：截图与多模态审核

固定保存：

- `desktop-initial.png`
- `desktop-after-send.png`
- `desktop-outbox.png`
- `mobile-initial.png`

截图目录：`docs/front_design/acceptance/<stage>/`。截图审核必须检查真实裁切、碰撞、遮挡和视觉层级，不能用 DOM 正确性替代。

## 9. 失败分类与处理方法

| 失败类型 | S1 实例 | 正确处理 | 禁止做法 |
| --- | --- | --- | --- |
| API 超时/5xx | 多轮主接口失败 | 保留失败记录，按相同请求重试并自动切备用 | 修改 prompt 后把两次结果当同一实验 |
| HTTP 成功但正文截断 | Batch 3、Batch 4 | 检查文件标记和结尾；缩小输出文件数；附上截断响应发修复轮 | 猜测缺失代码或直接集成半个文件 |
| 设计违反边界 | Round 3 暴露内部状态和假生成 | 单独发合规修订轮，明确 superseded | 只删几个词，保留错误状态模型 |
| 实现违反架构 | 回复硬编码在 controller | 将数据退回 Fixture，经 Adapter/ViewModel 传递 | 因为“只是原型”跳过分层 |
| DOM/安全问题 | `innerHTML`、随机 ID、未知角色升级 | 改为 DOM API、确定性 ID、未知字段过滤 | 相信模型说明中的“安全”自述 |
| 状态同步 bug | Dialog close 清空新 activeSpace | 区分用户关闭与同步关闭，补浏览器测试 | 只靠静态阅读判断 Dialog 正确 |
| 视觉问题 | 桌面露出海报文字、面部裁切 | 用实际截图 + 原图做多模态审核，再精确改 CSS | 根据 CSS 数值想象最终画面 |
| 验收工具缺失 | MCP Chrome 需要 sudo | 在项目外安装用户级 Chromium/Playwright | 向产品项目加入无关测试依赖或跳过浏览器验收 |
| 依赖或系统权限失败 | Chrome system install 被 sudo 拒绝 | 停止该安装路径，选择权限内的用户级工具 | 绕过权限或反复执行相同失败命令 |

失败恢复原则：

1. 不覆盖失败证据；
2. 不在失败时扩大任务范围；
3. 保持 prompt 和上下文可比较；
4. 输出截断时优先缩小交付文件数；
5. 代码问题由本地证据定位，不继续让模型自由重写整个阶段；
6. 修复后从最小相关 Gate 开始，并最终重跑全量验收。

## 10. S1 调用统计与可追溯索引

| 调用 | 尝试 | 成功端点 | 上下文文件 | 图片 | 作用 |
| --- | ---: | --- | ---: | ---: | --- |
| Round 1 | 1 | primary | 6 | 0 | 视觉方向 |
| Round 2 | 2 | backup | 7 | 0 | 组件与状态 |
| Round 3 | 1 | primary | 8 | 0 | 最终契约候选，后被修订 |
| Round 4 | 2 | backup | 6 | 0 | 合规修订契约 |
| Batch 1 | 1 | primary | 10 | 1 | 场景基础 |
| Batch 2 | 2 | backup | 11 | 1 | Fixture/ViewModel/AppState |
| Batch 3 | 1 | primary | 16 | 1 | 本地对话，响应截断 |
| Batch 3B | 6 | backup | 13 | 1 | 对话补全 |
| Batch 4 | 2 | backup | 16 | 1 | 四静态空间，CSS 截断 |
| Batch 5 | 2 | backup | 18 | 1 | 响应式与无障碍 |
| Visual Audit | 2 | backup | 12 | 4 | 实际截图视觉复核 |

完整 run 位于 `/home/wz/gemini-api-traces/runs/`。后续文档只记录 run label 或目录名，不复制 API 密钥和未经脱敏的配置。

## 11. 后续阶段标准执行流程

S2 及以后统一采用以下流程。

### Step 1：阶段定义

- 从 `frontend_architecture_v1.md` 和 API contract 提取明确范围；
- 列出本阶段必须交付、明确不做和安全禁区；
- 写出可通过浏览器/API mock 验证的 Definition of Done；
- 创建 `docs/front_design/acceptance/<stage>/`。

### Step 2：现状基线

- 检查当前代码和 dirty worktree，保留用户无关改动；
- 运行上一阶段全量验收；
- 固定当前截图和关键状态；
- 记录接口契约与后端实现差异。

### Step 3：设计拆轮

推荐至少三轮：

1. 体验与视觉方向；
2. 组件、数据、状态和错误体验；
3. 合规/安全修订与最终实现契约。

每轮都是无状态调用，必须重新附带权威文档和上轮必要结果。设计轮不直接写入产品代码。

### Step 4：实现拆批

每批建议限制为一个可独立验证的纵向能力和 3–6 个完整文件，例如：

1. API client 与 user-safe adapter；
2. `/api/state` 初始加载和降级；
3. `/api/chat` 成功流；
4. chat 失败、超时、离线和重试；
5. 响应式与可访问性；
6. 截图审核与精修。

不要让 Gemini 一次生成整个阶段，也不要要求它自行修改仓库。

### Step 5：每批审查

- 完整性 → 安全 → 架构 → 语法 → 浏览器；
- 只集成经过理解的代码；
- 对模型代码做的人工修正要记录原因；
- 一旦发现权威文档有问题，先更新文档再继续扩展。

### Step 6：故障恢复

- 网络失败：相同请求自动重试和主备切换；
- 截断：缩小文件范围并附带截断输出；
- 越界：发合规修订，而非直接进入实现；
- 行为 bug：先写可复现测试，再定向请求或本地修正；
- 视觉 bug：先生成真实截图，再发多模态审核；
- 权限问题：只使用授权范围内的替代工具。

### Step 7：阶段验收

- 静态扫描、单元/集成检查；
- 真实浏览器行为；
- desktop、mobile、keyboard-open、reduced-motion；
- 网络请求和响应字段安全检查；
- 控制台、错误态、重试态和焦点路径；
- 截图与 Gemini 多模态终审；
- 更新 acceptance README、架构决策与待决问题。

## 12. S2 特别注意事项

S2 会首次引入真实 `/api/state` 与 `/api/chat`，风险高于 S1。开始前必须：

- 保留现有 fixture adapter，新增 API adapter，不直接替换 ViewModel；
- 对后端 response 做严格白名单，默认丢弃未知字段；
- 明确禁止将内部 reasoning/action/debug 字段进入 AppState、DOM、日志和持久化；
- 将 idle、submitting、waiting、success、error、offline 设计为用户诚实可见的状态；
- 区分“请求已发送”“服务端已接受”“最终回复已呈现”，不能把 HTTP 200 简化为全部成功；
- 设计取消、超时、重试和重复提交策略；
- 明确刷新后对话恢复策略尚未由安全历史接口支持；
- 使用受控 mock 或本地后端做成功、慢响应、错误响应和恶意额外字段测试；
- S1 浏览器测试必须继续作为回归基线。

## 13. 阶段完成定义（Definition of Done）

一个后续阶段只有同时满足以下条件才算完成：

- 需求、非目标和安全边界已文档化；
- Gemini 每次输入输出均在项目外完整留痕；
- 所有响应经过完整性和越界审查；
- 代码遵循当前架构数据流；
- 自动检查和真实浏览器测试通过；
- 固定视口截图已人工和多模态审核；
- 失败路径而非只有 happy path 得到验证；
- 验收材料位于 `docs/front_design/acceptance/<stage>/`；
- 架构决策、接口差异和遗留问题已更新；
- 临时服务器关闭，旧文件和临时产品资产已清理；
- 最终交付说明可以从文件和 trace 独立复现。

## 14. S1 的核心经验

1. 高质量上下文比一次超长 prompt 更重要，但上下文不能代替任务拆分。
2. 设计需要视觉、组件和合规三个层次；“最终版”也必须接受安全审查。
3. API 成功、输出完整、代码正确、体验合格是四个不同结论。
4. 模型最容易把原型做成“像真的一样”的假网络流程，必须坚持展示真实性。
5. Fixture/ViewModel 边界在静态阶段就建立，能显著降低后续 API 接入风险。
6. 多模态审核必须使用真实浏览器截图；只发送原始设计图无法发现 CSS 裁切问题。
7. 重试机制必须保留失败证据并支持主备切换，不能只保留最后一次成功。
8. 后续阶段应继承 S1 的验收基线，而不是在引入后端后重新定义正确性。
