# S1 静态主场景垂直切片验收记录

完整过程复盘与后续阶段执行方法见 [S1 全流程复盘与后续阶段执行手册](../../S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md)。

验收日期：2026-07-25

## 交付范围

- 以 `companion.png` 为唯一主视觉资产的沉浸式桌面/移动主场景。
- Fixture → Adapter → ViewModel → AppState → DOM 的本地静态数据链路。
- 中文 IME 安全输入、同步本地 fixture 回复、最多保留 5 条成功消息。
- Today、Outbox、Memory、Privacy 四个原生 Dialog 静态空间。
- `visualViewport` 键盘态、reduced-motion、焦点回归、44px 移动触控目标。
- 不包含后端 API、持久化、CRUD、流式响应或模型请求。

## 自动验收结果

项目外 Playwright 验收脚本：`/home/wz/gemini-api-traces/browser-tools/verify-s1.mjs`

- JavaScript 模块语法检查通过。
- 未发现 `fetch`、XHR、WebSocket、storage、timer、`innerHTML` 等越界实现。
- 空输入禁用、IME 组合期 Enter 不提交、成功提交回复与场景色调更新通过。
- 消息上限、输入焦点恢复、四 Dialog 单实例打开/关闭、入口焦点恢复通过。
- 打开 Outbox 后未读数仍保持为 fixture 值，未伪造已读状态。
- reduced-motion 状态传递与移动触控目标检查通过。
- 浏览器控制台错误：0；外部/API 请求：0。

## 截图

- `desktop-initial.png`：1440×900 初始主场景。
- `desktop-after-send.png`：1440×900 本地发送后的场景。
- `desktop-outbox.png`：1440×900 来信空间。
- `mobile-initial.png`：390×844 初始主场景。

## Gemini 可追溯记录

所有请求、上下文副本、图片哈希、原始响应、重试与端点角色均保存在项目外目录：

`/home/wz/gemini-api-traces/runs/`

本轮实现批次标签：`luminous-s1-impl-batch1`、`batch2`、`batch3`、`batch3b`、`batch4`、`batch5`、`luminous-s1-visual-audit`。
