# 07 Gemini Implementation Prompt Template

下面模板用于下一阶段让 Gemini 写代码。每次只替换 `{BATCH_NAME}` 和 `{BATCH_SCOPE}`。

```text
你是「栖光 luminous」前端视觉重构的实现工程师。Codex 负责应用补丁、运行和验收；你负责产出本批次代码。

不要调用外部工具。不要引入 React/Vite/package.json。当前前端是单文件：

/home/wz/luminous/apps/companion-web/companion-ui/index.html

请基于以下 implementation pack：

- docs/front_design/implementation/00_implementation_brief.md
- docs/front_design/implementation/01_design_contract.md
- docs/front_design/implementation/02_existing_frontend_inventory.md
- docs/front_design/implementation/03_api_contract.md
- docs/front_design/implementation/04_target_dom_css_js_spec.md
- docs/front_design/implementation/05_implementation_batches.md
- docs/front_design/implementation/06_acceptance_checklist.md

本轮批次：{BATCH_NAME}

本轮范围：

{BATCH_SCOPE}

硬性要求：

- 保持 Vanilla HTML/CSS/JS。
- 输出 unified diff patch，或输出完整替换后的 index.html。
- 不要伪代码。
- 不要只写说明。
- 不要删除本批次之外的 API 能力。
- 不允许 system_thinking 进入 DOM。
- 不允许三栏工具台、卡片墙、密集聊天气泡。
- 保持 390x844 可用。

请在输出末尾列出：

1. 修改了哪些区域。
2. 保留了哪些 API。
3. 你认为 Codex 应如何验收。
```
