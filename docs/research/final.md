# 栖光 luminous 伴侣底座当前状态

栖光，是在某个人身边停驻的一束光。本文总结当前 companion runtime 的已有能力和剩余缺口；训练管线仍作为人格/模型底座保留，但产品主线已经进入情感陪伴实现阶段。

当前已有：

- state：见 [state.py](/home/wz/role-play/luminous/runtime/domain/state.py)，已扩展 relationship_arc / attachment / drives
- memory：见 [memory.py](/home/wz/role-play/luminous/runtime/domain/memory.py)，已具备 L0-L4、threads/links、memory_evidence、consolidation、编辑/遗忘/导出
- event ledger：见 [events.py](/home/wz/role-play/luminous/runtime/domain/events.py)，可按 trace_id 回放
- runtime 编排与主动 tick：见 [runtime.py](/home/wz/role-play/luminous/runtime/application/runtime.py)，已接 worker / jobs / outbox / feedback / webhook、Telegram、Bark 通知适配
- HTTP 能力接口：`/api/state`、`/api/memory`、`/api/ledger`、`/api/trace`、`/api/memory/evidence`、`/api/proactive/tick`、`/api/worker/tick`

## 现在底层还缺什么

### 1. 真正的分层记忆系统

现在的 memory 已经不是纯 JSONL：有 L0 原文、L1 抽取、L2/L3/L4 consolidation、FTS5、threads/links、编辑/遗忘/导出。最终还需要进一步接近 Paramecium / Aelios / Aura 这类结构：

- L0 原文层：每条用户/AI 原话永久保留，不能被摘要替代
- L1 摘录层：LLM 从对话中抽取“值得记住的事实/偏好/事件”，每条必须带原文证据
- L2 用户画像/关系画像：稳定事实、称呼、边界、偏好、重要人物
- L3 主题/事件层：把零散事实组织成“这段时间发生了什么”
- L4 长期归档层：旧会话不进实时上下文，但可召回

Paramecium 这点很值得学：原文是事实源，向量和摘要只是索引，不应该替代原话；它还让模型先看到“记忆目录”，再决定是否真正 recall 原文。([github.com](https://github.com/Shitsuten/paramecium))

我们现在仍缺：

- 向量 + BM25 混合检索
- 更细的跨主题、长程语义反转检测
- 更完整的 Dream Loop / consolidation 策略
- 记忆可视化审计面板

Aura 已经把长期记忆、对话后洞察、周期性 Dream Loop、情绪状态、关系模型和提醒串起来了，这是我们最终要追的方向。([github.com](https://github.com/gqy20/Aura))

### 2. 更完整的 state engine

现在 state 已经从几个数值扩展成“伴侣生命体征”的雏形：mood、energy、support_need、risk_level、relationship，再加 relationship_arc、attachment、drives。最终 state 还应该更完整：

- 用户状态：情绪、疲劳、压力、孤独、近期主题
- 关系状态：信任、熟悉、亲密、边界、依赖风险
- 伴侣状态：牵挂、疲惫、主动欲望、保护欲、当前节奏
- 场景状态：是睡前、工作中、刚结束冲突、长时间未联系、纪念日前后
- 安全状态：正常 / 关注 / 高风险 / 必须拦截

AI Companion Runtime 的做法可以借：先并行跑 intent / emotion / risk / memory，再进入 agent harness；高风险先拦截，普通情况再进入模型回复。([github.com](https://github.com/yf0522/ai-companion-runtime))

我们现在仍缺：

- 更细的 state transition 规则表
- 更独立的风险政策层
- 场景/关系弧的专项评估集
- 状态变化的可视化回放

### 3. Event ledger 还需要变成 trace system

现在 events.jsonl + SQLite ledger 已经能按 trace_id 回放，但还不算完整的 trace viewer。

最终 ledger 应该记录：

- 用户输入
- 记忆召回了什么
- 哪些记忆被注入 prompt
- state 如何变化
- 风险判断
- 模型请求与响应元数据
- 主动联系为什么 due / 为什么 hold
- 发送渠道、投递状态、用户是否回复
- 后台任务：记忆抽取、consolidation、提醒、导出

AI Companion Runtime 的 trace 设计比较完整：每次请求有 trace_id，记录意图、情绪、风险、记忆、模型、工具，并能查询完整链路。([github.com](https://github.com/yf0522/ai-companion-runtime))

我们现在仍缺：

- trace viewer / 可视化
- 成本 / token / 延迟统计
- LLM 调用原始 trace
- 面向调试的 trace drill-down

### 4. 主动联系机制还很初级

现在的 proactive 已经有 idle 时间、关系强度、support_need、energy、DND、cooldown、反馈学习、Bayesian-like 用户可用性估计、概率化触达 gate、出箱、真实外部通知适配和回执；但距离“像真人一样想起你”还差一步。

最终要像 revive-companion 那样拆成三阶段：

- 时机：Poisson / longing 概率，不是固定 cron
- 价值：信息增益，判断这次主动联系是否真的有意义
- 状态：贝叶斯推断用户此刻可能在忙、睡觉、空闲、需要关心等([github.com](https://github.com/pearthink123/revive-companion))

我们现在仍缺：

- 更细的 Bayesian 用户状态估计：基于真实回复历史、设备状态、日程、时区和用户手动偏好持续校准
- Web Push / 手机原生通知
- 主动联系 A/B 与效果指标
- 更细的消息类型分层

### 5. Scheduler / background worker

现在已经有 worker.py 和 `/api/worker/tick`，能跑 state_decay / proactive / memory jobs。最终还需要更生产化的后台系统：

- 每 15/30/60 分钟 tick
- 夜间记忆整理
- 纪念日提醒
- 日程提醒
- 长时间未互动关怀
- 失败重试
- 通知投递回执

Aura 用 Android WorkManager/AlarmManager 做提醒，AI Companion Runtime 用后台任务做记忆压缩、embedding、reflection 和 trace 写入，这两个方向都值得借。([github.com](https://github.com/gqy20/Aura)) ([github.com](https://github.com/yf0522/ai-companion-runtime))

我们现在仍缺：

- 常驻部署与健康监控
- 失败重试和告警策略
- 多进程/多实例下的调度协调

### 6. Prompt builder / context budget manager

现在已经有专门的 PromptBuilder。最终还需要更细的 context budget manager：

- 固定 persona
- 当前 state
- 关系摘要
- 最近工作记忆
- 相关长期记忆目录
- 必要时 recall 原文
- 安全约束
- 输出协议

核心目标是：不要每次把所有记忆塞进 prompt，而是先给“菜单”，让模型决定是否展开。这个很像 Paramecium 的 recall 工具思路。([github.com](https://github.com/Shitsuten/paramecium))

我们现在仍缺：

- 更细的 recall/menu 选择策略
- 对预算、召回、证据的自动权衡

### 7. 安全与边界系统

情感陪伴不是普通聊天，必须有底层安全约束：

- 自伤/自杀/暴力/极端依赖识别
- 不鼓励用户把 AI 当唯一支持
- 不诱导过度依赖
- 不伪装现实人类承诺
- 主动联系不能在高风险时乱发
- 危机响应要进入特殊流程

现在已经有分层 risk engine 和 proactive hold/watch 语义，后续还应该继续补安全 policy、emergency response template 和人工/现实支持建议。

### 8. 数据主权

未来用户一定要能：

- 查看记忆
- 修改记忆
- 删除记忆
- 导出全部数据
- 迁移到另一个模型 / 另一个前端
- 清空状态
- 查看“她为什么记住这个”

Awesome AI Companion 里把 continuity / data ownership 单列为长期伴侣基础设施方向，我们这里也应该变成底层能力，而不是 UI 附属功能。([github.com](https://github.com/DasterProkio/awesome-ai-companion/blob/main/README.md))

### 9. 测试数据怎么选

如果我们现在要给底层能力做回归测试，优先顺序我建议是：

- 记忆：AMemGym、LongMemEval、LoCoMo
- 画像 / 偏好：PersonaMem
- 情绪 / 同理：EmpatheticDialogues
- 主动联系：ProActEval、ProDial

更完整的来源和落地方式，见 [companion_eval_data_sources.md](/home/wz/role-play/docs/research/companion_eval_data_sources.md)。

当前进度与 `ai_companion_landscape.md` 的逐项差距审计，见 [ai_companion_progress_gap_audit.md](/home/wz/role-play/docs/research/ai_companion_progress_gap_audit.md)。
