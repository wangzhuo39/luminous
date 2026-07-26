你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮输出 Batch 3B：审计/调试入口、渐进式重构路线、完整验收清单。

方向：晶格温室。主体验必须沉浸，Trace/Ledger/Jobs 作为深层审计入口，不污染陪伴空间。当前前端是 /home/wz/luminous/apps/companion-web/companion-ui/index.html，Vanilla HTML/CSS/JS，Python 静态托管，无 React/Vite。Codex 后续负责实现和验收。

相关 API：GET /api/trace, GET /api/ledger, GET /api/jobs, GET /api/export。还有所有前面设计过的 chat/state/memory/outbox/reminders/calendar/today/tasks/routines/activities/diary/actions。

请输出中文 Markdown，结构：

# Batch 3B：审计调试、渐进式重构路线与验收清单

## 1. 审计与深层调试体验原则
- 为什么 trace/ledger/jobs 不进入主体验。
- 普通用户、开发者、隐私审计三种视角如何区分。

## 2. 组件规格：PrivacyAuditDrawer
覆盖 export、memory forget、隐私说明、可审计事件摘要、用户可理解文案。
写职责、DOM 建议、API 映射、状态、移动端、视觉细节、验收标准。

## 3. 组件规格：DebugTracePanel
覆盖 GET /api/trace、GET /api/ledger、GET /api/jobs。深层入口、快捷键、权限/显隐策略、高密度日志视图、性能影响、错误状态。

## 4. 从当前 index.html 到晶格温室的三阶段重构路线
阶段 1：视觉骨架。阶段 2：功能收纳。阶段 3：沉浸增强。
每阶段列：目标、保留 API 逻辑、替换 DOM 模块、替换 CSS 模块、JS 状态/函数组织、风险、验收标准、回滚点。

## 5. 建议 DOM 分区与 JS 状态模块
不要写完整代码，但给出文件内结构建议、CSS 变量分组、事件委托、fetch API 封装、状态 store、render 函数边界。

## 6. 性能预算与测试建议
覆盖首屏加载、图片资源、动画 FPS、内存、移动端、弱网、mock 模式、本地 smoke test、浏览器截图验收。

## 7. 完整设计验收清单
给 25-35 条可检查标准，覆盖视觉、交互、API 功能、安全隐私、移动端、可访问性、性能、沉浸感、非工具化。

## 8. 实施前决策清单
列出 Codex 开始改代码前需要确认或准备的事项，但不要向用户提问；用“建议默认值”形式给出。

要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
