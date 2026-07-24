# CLI Reference

本文档记录当前可用的本地命令、参数和推荐启动方式。命令默认从仓库根目录执行：

```bash
cd /data01/home/wz/role-play
```

本项目本地约定使用 `rtk proxy` 包一层 Python 命令，避免命令输出被过滤或截断：

```bash
rtk proxy python luminous/training/pipeline/cli.py <command> [options]
```

## 前后端联调

启动后端并由它托管前端：

```bash
rtk proxy luminous-api --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000`。后端默认读取 `.env` 中的 OpenAI-compatible 配置；只验证界面时可加 `--mock`：

```bash
rtk proxy luminous-api --host 127.0.0.1 --port 8000 --mock
```

接口：

- `GET /api/health`
- `POST /api/chat`，请求体为 `{"message": "...", "history": [...]}`，响应只包含 `role_thinking`、`role_action`、`reply`、`presence` 等安全字段。

## 主流程

`run` 是当前 txt-to-HER-SFT 主入口：

```bash
rtk proxy python luminous/training/pipeline/cli.py run \
  --input book.txt \
  --out outputs/all-new-pipline \
  --language zh \
  --concurrency 2 \
  --no-continue-on-failure
```

`run-staged` 是同一条 traceable staged pipeline 的别名：

```bash
rtk proxy python luminous/training/pipeline/cli.py run-staged \
  --input book.txt \
  --out outputs/all-new-pipline \
  --language zh \
  --concurrency 2 \
  --no-continue-on-failure
```

### `run` / `run-staged` 参数

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input INPUT` | 是 | - | 输入小说 `.txt` 文件。 |
| `--out OUT` | 是 | - | 输出目录，包含 prompt、LLM response、中间产物和最终 SFT 数据。 |
| `--chapters CHAPTERS` | 否 | 全书 | 只处理前 N 章；不传则处理全部章节。 |
| `--language {zh,en}` | 否 | `zh` | prompt 语言。 |
| `--profile PROFILE` | 否 | `docs/superpowers/profiles/yezhen-profile-v0001.md` | 角色 profile markdown。当前模块化主链路主要使用固定 profile/background 模块；旧 annotation/profile 实验仍会引用 profile。 |
| `--concurrency CONCURRENCY` | 否 | `4` | 每个 LLM batch 内部并发数。当前 stage 4/5/6 会同时运行，因此实际峰值并发约为 `3 * concurrency`。 |
| `--continue-on-failure` | 否 | 开启 | speaker attribution 失败后记录到 `failed_requests.jsonl` 并继续后续 stage。 |
| `--no-continue-on-failure` | 否 | - | speaker attribution 任一请求耗尽重试后直接停止，不进入后续 stage。全书生产更推荐使用这个开关，先保证 stage 2 归因完整。 |

### 自动续跑脚本

API 不稳定时可以用脚本守护全书任务。脚本会执行固定全书命令；若进程非 0 退出，等待 60 秒后重新启动；若正常完成则退出。

```bash
luminous/training/data/run_all_new_pipeline_until_done.sh
```

旧入口 `scripts/run_all_new_pipeline_until_done.sh` 仍作为兼容 wrapper 保留。

默认等价于：

```bash
rtk proxy python luminous/training/pipeline/cli.py run \
  --input book.txt \
  --out outputs/all-new-pipline \
  --language zh \
  --concurrency 6 \
  --no-continue-on-failure
```

可选环境变量：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `INPUT` | `book.txt` | 输入小说文本。 |
| `OUT` | `outputs/all-new-pipline` | 输出目录。 |
| `LANGUAGE` | `zh` | prompt 语言。 |
| `CONCURRENCY` | `6` | 传给 CLI 的并发数。 |
| `RESTART_DELAY_SECONDS` | `60` | 异常退出后的等待秒数。 |
| `MAX_RESTARTS` | `0` | 最大重启次数；`0` 表示不限。 |
| `LOG_DIR` | `$OUT/run_logs` | 每次尝试的日志目录。 |

## 断点续跑

LLM response 文件会按 `request_id` 复用已有成功结果。成功条件是该行存在 `response_json`，且没有 `error_type`、`error`、`parse_error`。

续跑时：

- 已成功的 request 会跳过。
- 缺失、失败或 parse error 的 request 会重试。
- `max_attempts` 表示本次进程启动后的新增尝试预算，不是历史 attempts 总上限。也就是说，某个 request 上次已经失败到 10 次，重跑时仍会从 attempt 11 开始继续尝试。
- 历史失败 attempts 会保留在 response 行里，方便追踪问题；成功 response 会覆盖错误状态并继续下游流程。
- `failed_requests.jsonl` 会按当前仍失败的 response 行重写；历史失败项如果续跑成功，会从失败文件中移除。
- `system_contexts`、`user_contexts`、`assistant_responses` 三个模块化 stage 也按各自 `llm_responses/04_*`、`05_*`、`06_*` 文件断点续跑；根目录下的派生 JSONL 会在 LLM response 补齐后重新生成。

全书续跑时，若补跑了 `speaker_attribution` 失败项，建议清掉下游 stage 4/5/6 response 后重建，因为新归因可能改变 `sft_turns`：

```bash
rm -f outputs/all-new-pipline/llm_responses/04_system_contexts.jsonl
rm -f outputs/all-new-pipline/llm_responses/05_user_contexts.jsonl
rm -f outputs/all-new-pipline/llm_responses/06_assistant_responses.jsonl
```

如果只改了 assistant prompt，例如 `role_thinking` 风格或 `role_action` 长度约束，只需要重跑 stage 6 和后续派生文件。先删除旧的 06 prompt/response 和最终 SFT/HER 产物，保留 stage 02/04/05：

```bash
rm -f outputs/all-new-pipline/prompt_requests/06_assistant_responses.jsonl
rm -f outputs/all-new-pipline/llm_responses/06_assistant_responses.jsonl
rm -f outputs/all-new-pipline/assistant_responses.jsonl
rm -f outputs/all-new-pipline/sft_messages_draft.jsonl
rm -f outputs/all-new-pipline/sft_messages_audit.jsonl
rm -f outputs/all-new-pipline/sft_messages_trainable.jsonl
rm -f outputs/all-new-pipline/sft_messages_her.jsonl
rm -f outputs/all-new-pipline/review_queue.jsonl
```

然后重新运行主流程；已有的 speaker/system/user LLM response 会按断点跳过，新的 06 prompt 会按当前代码重新生成。

## 只准备 prompt

`prepare-prompts` 只做确定性候选抽取和 speaker attribution prompt 准备，不调用 LLM：

```bash
rtk proxy python luminous/training/pipeline/cli.py prepare-prompts \
  --input sample_short.txt \
  --out outputs/sample_short \
  --chapters 2 \
  --language zh
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input INPUT` | 是 | - | 输入小说 `.txt` 文件。 |
| `--out OUT` | 是 | - | 输出目录。 |
| `--chapters CHAPTERS` | 否 | `3` | 只处理前 N 章。 |
| `--language {zh,en}` | 否 | `zh` | prompt 语言。 |

## 单独调用 LLM

`call-llm` 可以对任意 prompt request JSONL 单独调用 OpenAI-compatible LLM：

```bash
rtk proxy python luminous/training/pipeline/cli.py call-llm \
  --input outputs/all-new-pipline/prompt_requests/05_user_contexts.jsonl \
  --output outputs/all-new-pipline/llm_responses/05_user_contexts.jsonl \
  --concurrency 2
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input INPUT` | 是 | - | prompt request JSONL。 |
| `--output OUTPUT` | 是 | - | LLM response JSONL。 |
| `--concurrency CONCURRENCY` | 否 | `1` | 并发请求数。 |

## 单独 QA

`qa-sft` 对已有 `sft_messages_draft.jsonl` 执行 deterministic QA，并导出 trainable / HER / review queue：

```bash
rtk proxy python luminous/training/pipeline/cli.py qa-sft \
  --input outputs/all-new-pipline/sft_messages_draft.jsonl \
  --out outputs/all-new-pipline
```

参数：

| 参数 | 必填 | 说明 |
|---|---:|---|
| `--input INPUT` | 是 | SFT message draft JSONL。 |
| `--out OUT` | 是 | QA 输出目录。 |

当前 system_context / assistant_response 的语义类检查只建议作为 audit/warning 使用。由于目标台词复述、动作细节和上下文线索很容易出现误判，主流程不会自动删除这些 response，也不会自动打回重跑。

## SFT 数据工具

这些命令不属于 `roleplay_pipeline.cli`，而是训练前的数据整理工具。

### Inspect

```bash
rtk proxy python luminous/training/data/sft_messages.py inspect \
  --input outputs/all-new-pipline/sft_messages_her.jsonl \
  --out outputs/all-new-pipline/sft_inspect_summary.jsonl \
  --samples 5
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input INPUT` | 是 | - | HER message JSONL。 |
| `--out OUT` | 否 | 无 | 输出 inspect summary JSONL。 |
| `--samples SAMPLES` | 否 | `5` | 抽样数量。 |

### Split

```bash
rtk proxy python luminous/training/data/sft_messages.py split \
  --input outputs/all-new-pipline/sft_messages_her.jsonl \
  --out outputs/all-new-pipline/sft_splits \
  --train 0.9 \
  --valid 0.05 \
  --test 0.05 \
  --seed 42 \
  --by chapter
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input INPUT` | 是 | - | HER message JSONL。 |
| `--out OUT` | 是 | - | split 输出目录。 |
| `--train TRAIN` | 否 | `0.9` | train 比例。 |
| `--valid VALID` | 否 | `0.05` | valid 比例。 |
| `--test TEST` | 否 | `0.05` | test 比例。 |
| `--seed SEED` | 否 | `42` | 随机种子。 |
| `--by {chapter,row}` | 否 | `chapter` | 默认按章节切分，降低相邻剧情泄漏。 |

### Export LLaMA-Factory

```bash
rtk proxy python luminous/training/data/sft_messages.py export-llamafactory \
  --input-dir outputs/all-new-pipline/sft_splits \
  --out outputs/all-new-pipline/llamafactory \
  --dataset-prefix yezhen_her \
  --base-model Qwen3-7B
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `--input-dir INPUT_DIR` | 是 | - | `split` 生成的目录。 |
| `--out OUT` | 是 | - | LLaMA-Factory 数据目录。 |
| `--dataset-prefix DATASET_PREFIX` | 否 | `yezhen_her` | dataset 名称前缀。 |
| `--base-model BASE_MODEL` | 否 | `Qwen3-7B` | manifest 记录的 base model。 |

## 环境变量

LLM 调用读取 OpenAI-compatible 配置，支持 `.env` 或环境变量。常用键包括：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT`
- `OPENAI_MAX_TOKENS`

当前本地 `.env` 也使用了小写别名键：`base_url`、`key`、`model`。

后端也支持 `ROLE_PLAY_BASE_URL`、`ROLE_PLAY_API_KEY`、`ROLE_PLAY_MODEL`、`ROLE_PLAY_TIMEOUT`、`ROLE_PLAY_MAX_TOKENS`、`ROLE_PLAY_TEMPERATURE` 和 `ROLE_PLAY_MOCK`。
