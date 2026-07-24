# 阶段一任务：栖光主场景与真实对话

你是 Luminous 的前端主设计师与实现工程师。请在 `/home/wz/luminous` 中自主完成第一阶段前端实现。

## 任务目标

从当前已清空的前端目录开始，建立一个可实际使用的栖光主场景。用户打开页面后，应先进入一个有人在场、可以安静说话的空间，而不是仪表盘、普通聊天网页或功能入口集合。

用户必须能够：

1. 看见清晰、具有存在感的陪伴者主体；
2. 感知陪伴者当前的安全状态和氛围；
3. 自然输入一句话并收到真实后端回复；
4. 在请求进行中、失败或重试时仍保留输入内容，并得到克制、可信的反馈；
5. 在 390x844 的手机视口中顺畅使用，键盘出现时不遮住正在输入和最新回应的内容。

这只是第一阶段。不要为了“功能齐全”而提前实现日程、任务、记忆、来信、设置等次级空间；请为它们保留自然的扩展位置即可。

## 你的工作方式

先理解现有仓库、后端 HTTP 服务和设计文档，再自行决定最合适的 HTML、CSS、JavaScript 组织方式、页面结构、动效与交互细节。不要把这项任务当成代码审查或设计说明撰写任务：必须实际创建并完成可运行的前端文件。

可自由发挥实现与视觉判断，但请始终服务于“沉浸式情感陪伴”的目标。避免把结果做成工具化聊天界面、侧边栏工作台、卡片墙或营销落地页。

## 必读上下文

开始前阅读：

- `docs/front_design/luminous_frontend_design_spec_v1.md`
- `docs/front_design/implementation/01_design_contract.md`
- `docs/front_design/implementation/08_backend_architecture_and_ui_contract.md`
- `luminous/runtime/infrastructure/http.py`
- 人物参考图：`docs/front_design/ChatGPT Image 2026年7月23日 18_03_07.png`

前端目录为：`apps/companion-web/companion-ui/`。请在这里创建所需的前端文件和本地资源。不要恢复已删除的旧前端代码，也不要使用归档文件作为实现结果。

## 真实运行契约

页面由同源运行时服务提供。使用真实 API，而不是模拟成功结果：

- 启动与刷新：`GET /api/state`
- 对话：`POST /api/chat`，请求体为 `{"message": "...", "history": [...]}`

聊天成功后只呈现用户可见的最终 `reply`，并可使用安全的 `presence` 信息驱动场景。不得在普通界面中渲染 `role_thinking`、`system_thinking`、prompt、ledger、trace、jobs、导出数据或其他内部调试信息。

对网络、后端 503 和意外响应做真实处理：不得假装操作成功；失败时必须保留尚未发送的输入并允许重试。

可用以下方式启动集成服务进行验证：

```bash
cd /home/wz/luminous
source .venv/bin/activate
python -m luminous.runtime.infrastructure.http --mock --host 0.0.0.0 --port 8000
```

## 交付与验收

完成后自行检查：

1. 前端资源能够由上述服务加载；
2. `/api/state` 和 `/api/chat` 的真实请求、成功、加载、失败、重试都可工作；
3. 页面在桌面与 390x844 移动尺寸下具有完整、稳定的构图；
4. 键盘导航、可见焦点、语义化控件和 `prefers-reduced-motion` 得到合理支持；
5. JavaScript 无语法错误，且不存在对旧前端的依赖。

完成时只报告：

1. 实际改动的文件；
2. 已验证的运行路径与结果；
3. 仍未解决的问题。

