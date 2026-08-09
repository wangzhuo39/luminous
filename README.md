# 栖光 luminous

栖光，是在某个人身边停驻的一束光。

`luminous` 是一个情感陪伴 AI 产品底座。当前项目已经从“小说角色训练数据准备”进入“AI 伴侣运行时实现”阶段：训练管线仍然负责把小说角色的人格训练进模型内部，而 `roleplay_companion` 负责长期陪伴所需的记忆、关系状态、主动联系、通知和可审计运行时。

产品身份见 [docs/product/luminous_identity.md](docs/product/luminous_identity.md)。

## 当前重点

现在优先建设的是情感陪伴底座：

- 长期记忆：L0 原文、L1 摘录、L2/L3/L4 consolidation、原文证据、记忆线程/链接、编辑/遗忘/导出。
- 状态引擎：情绪、意图、风险、场景、关系弧、依恋、驱动力、open loops、可解释状态转移。
- 主动联系：DND、cooldown、用户可用性估计、概率触达、outbox、webhook / Telegram / Bark 通知和反馈学习。
- PromptBuilder：记忆目录、必要证据展开、状态摘要、关系摘要、输出协议和预算信息。
- Worker / Trace：后台 tick、记忆整理、状态衰减、主动联系、outbox 投递、ledger / trace。

当前产品端为 Android App：核心陪伴、生活流、静默空间、系统通知和受限深链均由 Capacitor 客户端承载，并以“晶格温室”作为统一视觉基线。公网浏览器客户端已退役，只保留 Android 安装包下载页；网页资源继续作为 App 的共享 UI 源码与本地自动化测试基座。

## 项目边界

- `luminous/runtime/`：栖光情感陪伴运行时。
- `apps/companion-android/` 与 `android/`：Android 产品客户端、构建说明和原生工程。
- `apps/companion-web/`：App 共享 UI 源码及本地浏览器验收基座，不再作为公网产品端。
- `docs/front_design/`：前端设计理念、living architecture、S1–S5 实施记录和截图验收证据。
- `docs/product/`：产品身份、命名和产品阶段文档。
- `docs/research/`：AI 伴侣调研、进度审计、评测数据来源。
- `docs/architecture/`：伴侣底座架构和阶段路线图。
- `luminous/training/pipeline/`：小说文本到 HER-style SFT 数据生成；现在作为人格/模型底座能力。
- `luminous/training/data/`：训练数据检查、切分、导出和 companion seed data 准备。
- `luminous/training/finetune/`：本地 LoRA 训练、推理/评估工具和训练配置。

Compatibility wrappers remain in `tools/` and `scripts/` for older commands, but new code should use the directories above.

## 构建栖光 Android App

后端读取 `.env` 或环境变量中的 OpenAI-compatible 配置：

- `OPENAI_BASE_URL` or `base_url`
- `OPENAI_API_KEY` or `key`
- `OPENAI_MODEL` or `model`

构建可安装的 Android 内测包：

```bash
npm run android:build:debug
```

安装到已连接的设备：

```bash
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Android 本地提醒、前台 WebSocket 实时陪伴、后台漏信同步与正式签名流程见 [Android 客户端说明](apps/companion-android/README.md)。公网 `https://app.havilume.me/` 仅提供 App 下载提示，`/api/*`、`/api/realtime/outbox` 和 `/downloads/*` 保持服务。

本地开发或浏览器自动化仍可启动共享 UI：

```bash
luminous-api --host 127.0.0.1 --port 8000
```

然后仅在本机打开：

```text
http://127.0.0.1:8000
```

只查看确定性 fixture、避免调用后端接口：

```text
http://127.0.0.1:8000/?mode=fixture
```

本地网页模式不是产品发布渠道，仅用于确定性 fixture、接口联调和 Chromium 验收。

本地不调用 LLM 的 smoke test：

```bash
luminous-api --host 127.0.0.1 --port 8000 --mock
```

常用 API：

- `POST /api/chat`
- `GET /api/state`
- `GET /api/memory`
- `GET /api/memory/threads`
- `GET /api/memory/links`
- `GET /api/memory/evidence`
- `POST /api/memory/update`
- `POST /api/memory/forget`
- `GET /api/ledger`
- `GET /api/trace`
- `GET /api/outbox`
- `POST /api/proactive/tick`
- `POST /api/outbox/feedback`
- `POST /api/outbox/receipt`
- `GET /api/export`

公开 API 通过 user-safe DTO 输出；内部思考、prompt、ledger、trace、原始消息和 job 数据不会进入普通产品响应。公网部署使用显式 Origin、Bearer/会话认证和服务端会话绑定的通知设备。

## 后台 worker

运行一次 worker tick：

```bash
luminous-worker --once
```

运行指定 job：

```bash
luminous-worker --job memory_consolidation
```

当前周期任务包括：

- `state_decay_tick`
- `proactive_tick`
- `reminder_due_tick`
- `routine_due_tick`
- `activity_expiry_tick`
- `life_flow_effect_delivery`
- `life_flow_audit_delivery`
- `outbox_delivery`
- `runtime_maintenance`
- `memory_consolidation`
- `memory_reindex`

## 当前文档入口

建议新进入项目时按这个顺序读：

1. [docs/product/luminous_identity.md](docs/product/luminous_identity.md)：理解“栖光 luminous”的产品身份。
2. [docs/project_overview.md](docs/project_overview.md)：理解当前项目阶段和整体结构。
3. [docs/architecture/luminous_companion_runtime_architecture.md](docs/architecture/luminous_companion_runtime_architecture.md)：查看下一代 Companion Runtime 的规范性目标架构和模块边界。
4. [docs/research/ai_companion_progress_gap_audit.md](docs/research/ai_companion_progress_gap_audit.md)：查看当前完成度和缺口。
5. [docs/research/ai_companion_landscape.md](docs/research/ai_companion_landscape.md)：查看开源 AI 伴侣功能调研。
6. [docs/architecture/roleplay_companion_architecture.md](docs/architecture/roleplay_companion_architecture.md)：理解伴侣底座的早期设计。
7. [docs/architecture/companion_foundation_implementation_roadmap.md](docs/architecture/companion_foundation_implementation_roadmap.md)：查看阶段性实现路线。
8. [docs/front_design/README.md](docs/front_design/README.md)：查看前端设计与 S1–S5 文档索引。
9. [docs/front_design/FRONTEND_AGENT_HANDOFF.md](docs/front_design/FRONTEND_AGENT_HANDOFF.md)：查看当前前端完成状态、边界与后续接手规则。
10. [docs/front_design/frontend_architecture_v1.md](docs/front_design/frontend_architecture_v1.md)：查看持续维护的前端架构决策。

训练和数据准备文档仍然保留，但它们现在是“人格/模型底座”的资料，不再是产品主线入口：

- [docs/training/her_pipeline_analysis.md](docs/training/her_pipeline_analysis.md)
- [docs/training/modular_message_pipeline.md](docs/training/modular_message_pipeline.md)
- [docs/training/qwen3_7b_sft_preparation.md](docs/training/qwen3_7b_sft_preparation.md)
- [docs/cli_reference.md](docs/cli_reference.md)

## 训练管线仍然做什么

小说角色拟合仍然重要：它负责把叶筝这类小说角色的人格、边界、语气和行为分布训练进模型内部，而不是运行时靠 prompt 临时扮演。

完整 txt-to-HER-SFT pipeline 仍可运行：

```bash
python luminous/training/pipeline/cli.py run \
  --input sample_short.txt \
  --out outputs/sample_short \
  --chapters 2 \
  --language zh \
  --concurrency 2 \
  --no-continue-on-failure
```

主要输出：

- `sft_messages_her.jsonl`
- `sft_messages_trainable.jsonl`
- `review_queue.jsonl`
- `system_contexts.jsonl`
- `user_contexts.jsonl`
- `assistant_responses.jsonl`
- `failed_requests.jsonl`

训练数据检查、切分和 LLaMA-Factory 导出仍在 `luminous/training/data/sft_messages.py`。

## 验证

安装前端测试依赖：

```bash
npm ci
```

运行前端纯逻辑、契约和静态服务器测试：

```bash
npm run test:frontend
```

在 `http://127.0.0.1:4173` 已启动当前网页后，运行九套跨阶段 Chromium 验收：

```bash
npm run test:browser
```

最近一次验证结果（2026-07-26）：

```text
Node tests: 175 passed, 0 failed
Chromium acceptance: 9/9 scripts passed
Gemini S5 multimodal re-audit: 98/100, no P0/P1/P2
```

生成的 `outputs/` 目录默认被 git 忽略。
