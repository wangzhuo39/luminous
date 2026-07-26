# 栖光前端实现文档包

这个目录是给 Gemini 进入代码撰写阶段使用的 implementation pack。

它不是完整设计稿的替代品，而是把 `../luminous_frontend_design_spec_v1.md` 压缩成可执行的工程约束：改哪个文件、保留哪些 API、首屏应该长什么样、分几批实现、Codex 如何验收。

## 使用顺序

1. `00_implementation_brief.md`
2. `01_design_contract.md`
3. `02_existing_frontend_inventory.md`
4. `03_api_contract.md`
5. `08_backend_architecture_and_ui_contract.md` (以实际后端源码核验后的集成基线)
6. `04_target_dom_css_js_spec.md`
7. `05_implementation_batches.md`
8. `06_acceptance_checklist.md`
9. `07_gemini_implementation_prompt_template.md`

## 工作分工

- Gemini：负责前端代码第一稿、视觉表达、组件结构、CSS/JS 组织建议。
- Codex：负责调度 Gemini、应用补丁、修复集成问题、运行 mock、截图与验收。

## 重要边界

- 当前先不引入 React/Vite/package.json。
- 第一阶段仍在 `apps/companion-web/companion-ui/index.html` 内完成。
- 不允许暴露 `system_thinking`。
- 不允许回到三栏工具台、卡片墙、密集聊天气泡。
- Gemini 原始设计稿仍保留在 `../gemini_luminous_frontend_*.md`。
