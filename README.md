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

当前网页端已完成 S1–S5：核心陪伴、生活流、静默空间与 PWA 产品化能力均已落地，并以“晶格温室”作为统一视觉基线。后续仍可演进为 app、Live2D/VRM、语音和更完整的伴侣空间，但新能力必须先建立用户安全接口与隐私边界。

## 项目边界

- `luminous/runtime/`：栖光情感陪伴运行时。
- `apps/companion-web/`：当前可运行网页端，包含晶格温室主场景、生活流、静默空间与 PWA 壳层。
- `docs/front_design/`：前端设计理念、living architecture、S1–S5 实施记录和截图验收证据。
- `docs/product/`：产品身份、命名和产品阶段文档。
- `docs/research/`：AI 伴侣调研、进度审计、评测数据来源。
- `docs/architecture/`：伴侣底座架构和阶段路线图。
- `luminous/training/pipeline/`：小说文本到 HER-style SFT 数据生成；现在作为人格/模型底座能力。
- `luminous/training/data/`：训练数据检查、切分、导出和 companion seed data 准备。
- `luminous/training/finetune/`：本地 LoRA 训练、推理/评估工具和训练配置。

Compatibility wrappers remain in `tools/` and `scripts/` for older commands, but new code should use the directories above.

## 启动栖光网页端

后端读取 `.env` 或环境变量中的 OpenAI-compatible 配置：

- `OPENAI_BASE_URL` or `base_url`
- `OPENAI_API_KEY` or `key`
- `OPENAI_MODEL` or `model`

启动后端和静态网页：

```bash
luminous-api --host 127.0.0.1 --port 8000
```

然后打开：

```text
http://127.0.0.1:8000
```

只查看确定性 fixture、避免调用后端接口：

```text
http://127.0.0.1:8000/?mode=fixture
```

网页端提供 Manifest、可安装 PWA、静态离线壳和空间级深链。离线只保证温室轮廓与未发送 session draft；业务 API、聊天、写操作和历史不会缓存，也不会排队伪发送。

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

`POST /api/chat` 当前仍可能返回 `role_thinking`、`role_action`、memory、prompt、ledger/meta 等普通产品界面不应消费的内部字段。网页端通过严格 adapter 白名单只保留最终回复与有限 scene presentation；raw response 不进入 AppState、DOM、storage 或日志。公开部署前仍建议由后端提供真正的 user-safe DTO，并补齐身份认证与多用户隔离。

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
- `outbox_delivery`
- `memory_consolidation`
- `memory_reindex`

## 当前文档入口

建议新进入项目时按这个顺序读：

1. [docs/product/luminous_identity.md](docs/product/luminous_identity.md)：理解“栖光 luminous”的产品身份。
2. [docs/project_overview.md](docs/project_overview.md)：理解当前项目阶段和整体结构。
3. [docs/research/ai_companion_progress_gap_audit.md](docs/research/ai_companion_progress_gap_audit.md)：查看当前完成度和缺口。
4. [docs/research/ai_companion_landscape.md](docs/research/ai_companion_landscape.md)：查看开源 AI 伴侣功能调研。
5. [docs/architecture/roleplay_companion_architecture.md](docs/architecture/roleplay_companion_architecture.md)：理解伴侣底座架构。
6. [docs/architecture/companion_foundation_implementation_roadmap.md](docs/architecture/companion_foundation_implementation_roadmap.md)：查看五阶段实现路线。
7. [docs/front_design/README.md](docs/front_design/README.md)：查看前端设计与 S1–S5 文档索引。
8. [docs/front_design/FRONTEND_AGENT_HANDOFF.md](docs/front_design/FRONTEND_AGENT_HANDOFF.md)：查看当前前端完成状态、边界与后续接手规则。
9. [docs/front_design/frontend_architecture_v1.md](docs/front_design/frontend_architecture_v1.md)：查看持续维护的前端架构决策。

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
