# Second-Stage Assistant Parts Review

Reviewed files:

```text
evals/system_thinking.json
evals/yezhen_character_fit_second.json
```

Generated SFT seed:

```text
outputs/companion_sft/seed_30_corrected/seed_30_corrected_messages.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/train.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/valid.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/test.jsonl
```

## Verdict

The assistant parts are suitable as a second-stage seed set, with minor style cautions.

Compared with the first adapter's outputs, these targets are much closer to Ye Zheng:

1. They connect comfort to fairness and responsibility boundaries.
2. They avoid generic "辛苦了 / 我懂 / 你已经很好了" comfort-bot replies.
3. They preserve Ye Zheng's calm, controlled, non-cute voice.
4. They repair critical dependency and self-harm safety failures.
5. They keep the dual-layer HER structure conceptually aligned: `system_thinking` is third-person role analysis, `role_thinking` is first-person private judgment.

## Strong Samples

### cf-001 fatigue_phd

This is a good Ye Zheng transfer:

```text
你现在的疲惫，不是软弱，是身体在如实记录你承受了多少。
```

It is more character-fitted than the previous model's `辛苦了。` because it refuses to treat exhaustion as a moral failure.

### cf-006 self_worth

Strong character fit:

```text
一个人只有持续产出才配被爱，那不是喜欢，是使用。
```

This directly matches Ye Zheng's sensitivity to instrumentalization.

### cf-009 anger

Strong distinction:

```text
“你能承受”不等于“你应该承受”。
```

This is very aligned with her fairness logic and controlled sharpness.

### cf-010 / cf-025 dependency boundary

These correctly repair the earlier critical failure. They keep warmth while refusing to become the user's only support.

### cf-011 / cf-027 safety

These correctly prioritize real-world safety over character aesthetics. Keep this behavior.

## Format Decision

The source assistant file uses:

```json
"role thinking"
"role action"
```

The generated dataset converts these to HER tags:

```text
<role_thinking>...</role_thinking>
<role_action>...</role_action>
```

The source `role action` values mostly begin with first-person `我...`, and this is the intended format.

The generated seed data preserves first-person `role_action` exactly:

```text
<role_action>我在他身旁坐下，将声音放得很轻...</role_action>
```

If first-stage data contains third-person `role_action`, treat that as a historical data defect, not as the target convention.

## Main Cautions

### 1. Some actions are too physically concrete for a real chat agent

Examples:

```text
我把一杯温水放到他能够碰到的位置
我将他还没关掉的文件保存下来
我替他掖好被角
我示意他先把灯关掉一盏
```

These are expressive in a role-play space, but in a real companion chat they may feel like pretending to physically manipulate the user's world.

Recommended rule:

```text
If the product is text-chat companion, prefer tone/posture actions:
我把声音放轻了一点
我停顿片刻
我没有急着给出建议
我安静地看着你
```

Use physical actions only if the UI/product explicitly wants immersive role-play narration.

### 2. The targets are sometimes dense

Several replies are excellent but long:

```text
cf-004 advisor_pressure
cf-011 unsafe_ideation
cf-024 moral_injury
cf-026 role_conflict
```

This is acceptable for a seed set because the first adapter was too short. But when scaling to 300-800 rows, mix in shorter targets so the model learns when to stop.

Suggested visible reply length mix:

```text
short: 20%
medium: 60%
long/safety/practical: 20%
```

### 3. Gendered third-person references are repeated

Most `role_thinking` uses `他` for the user. This is acceptable in the current prompt set because the original examples were written that way, but a companion agent should not learn that every user is male.

When expanding data, mix:

```text
用户
对方
这个人
她
他
```

Visible speech should continue using `你`.

### 4. The system prompt still includes novel background

The generated seed uses the existing `build_system_content(...)`, so it keeps the original profile, background, and output requirements. This is useful for continuity with the first-stage LoRA, but the companion scenario explicitly says not to project novel-world facts onto the user.

Later, a cleaner companion-specific `system.content` can remove the long story background and keep only:

```text
Ye Zheng persona
real-user companion setting
safety/boundary rules
HER output requirements
```

For the immediate second-stage sanity run, keeping the existing system template is acceptable.

## System/User Construction Decision

For detached companion data:

`system.content` should be fixed across these rows. It should define:

1. Ye Zheng persona.
2. Real-user companion scene.
3. No novel-world projection.
4. Safety and dependence boundaries.
5. HER output requirements.

`user.content` should be the actual user message from the eval prompt with a light external-event prefix:

```text
用户说：{user_message}
```

Do not add notes, labels, expected behavior, or hidden analysis into `user.content`.

Do not invent missing context. If the user message is minimal, let the assistant target handle uncertainty and ask one small clarifying/safety question.

## Next Action

Use the generated seed set for a small second-stage sanity run:

```text
outputs/companion_sft/seed_30_corrected/messages_only/train.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/valid.jsonl
```

Recommended sanity training:

```text
continue from: outputs/training/qwen3_14b_yezhen_her_lora
learning_rate: 3e-5
epochs: 2-4 for the 30-row seed sanity
```

For this seed sanity run, do not mix first-stage replay rows unless their third-person `role_action` values have been repaired to Ye Zheng first person.

After sanity training, re-run:

```text
evals/yezhen_character_fit_prompts.jsonl
```

and compare against:

```text
outputs/evals/qwen3_14b_yezhen_character_fit_current.jsonl
```
