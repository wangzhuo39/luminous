# 栖光 luminous 评测数据来源清单

这份文档只回答一件事：如果我们现在要给 **栖光 luminous** 的情感陪伴底层能力做回归测试，哪些公开数据最值得先用。

结论先行：

- 记忆主基准先用 `AMemGym`。
- 长上下文 / 多会话记忆再补 `LongMemEval`、`LoCoMo`。
- 动态用户画像和偏好演化用 `PersonaMem`。
- 情绪承接和同理回应用 `EmpatheticDialogues`。
- 主动联系 / 主动介入用 `ProActEval`、`ProDial`。
- 真正的伴侣场景，还要再加一份我们自己的合成测试集。

## 1. 各数据集适合测什么

| 数据集 | 官方来源 | 适合测什么 | 对我们最有用的点 |
|---|---|---|---|
| AMemGym | https://agi-eval-official.github.io/amemgym/ | 交互式长程记忆、on-policy 记忆评测 | 最适合检验“写入 / 召回 / 利用”闭环 |
| LongMemEval | https://xiaowu0162.github.io/long-mem-eval/ | 多会话记忆、时间推理、知识更新、拒答 | 最适合检验长会话、更新、时间线 |
| LoCoMo | https://snap-research.github.io/locomo/ | 超长对话记忆、事件总结、多模态对话 | 最适合检验事件链和会话连续性 |
| PersonaMem | https://github.com/bowen-upenn/PersonaMem / https://huggingface.co/datasets/bowen-upenn/PersonaMem | 动态画像、偏好演化、个性化回应 | 最适合检验关系状态和用户偏好变化 |
| EmpatheticDialogues | https://github.com/facebookresearch/EmpatheticDialogues / https://huggingface.co/datasets/facebook/empathetic_dialogues | 情绪识别、同理回应 | 最适合检验 state engine 里的情绪承接 |
| ProActEval | https://huggingface.co/datasets/Team-ACE/ProActEval | 主动需求预测、提前介入 | 最适合检验主动联系的触发条件 |
| ProDial | https://aclanthology.org/2022.lrec-1.339.pdf | 主动对话动作：None / Notification / Suggestion / Intervention | 最适合检验主动动作类型和打扰强度 |

## 2. 为什么 AMemGym 适合先上

AMemGym 和我们当前目标最接近的地方，不是它“能背答案”，而是它把记忆评测做成了互动式流程：

- assistant 会参与对话，而不是只做离线问答
- 数据里有结构化 state 演化
- 评测指标直接覆盖 write / read / utilization

这和我们现在的三层目标正好对得上：

- 记忆：看能不能写对、记对、用对
- state engine：看状态是否随交互真实变化
- 主动联系：看长期沉默后是否能合理触达

## 3. 推荐的内部评测顺序

### 第一档：先跑起来

1. AMemGym base 作为主记忆基准
2. LongMemEval-S 作为长上下文补测
3. PersonaMem 作为画像 / 偏好演化补测

### 第二档：补 state 与情绪

1. EmpatheticDialogues 作为情绪与同理回应基准
2. PersonaMem 的动态偏好样本作为关系状态基准
3. 我们自己的 companion 场景集，补“陪伴语气、边界、依恋、修复”

### 第三档：补主动联系

1. ProActEval 测“何时主动”
2. ProDial 测“主动动作强度”
3. 结合我们自己的 idle / DND / 冷却 / 反馈闭环做最终验收

## 4. 对我们项目的直接落地方式

建议把评测拆成三类 fixture：

- `memory_*.jsonl`：来自 AMemGym / LongMemEval / LoCoMo / PersonaMem 的问答或会话切片
- `state_*.jsonl`：来自 PersonaMem / EmpatheticDialogues 的情绪、偏好、关系演化样本
- `proactive_*.jsonl`：来自 ProActEval / ProDial 的主动联系触发样本

然后再补一份我们自己的 `companion_scenarios.jsonl`，专门覆盖：

- 喜欢的小说角色拟合后的语气一致性
- 长期关系推进
- 纪念日 / 失联 / 睡前 / 饭点
- 边界感与依恋风险
- 主动联系后的用户反馈学习

## 5. 现在的建议

如果只选一个起点：先用 AMemGym。

如果要把三层能力一起测起来：AMemGym + LongMemEval + PersonaMem + ProActEval。

如果要接近最终 AI 伴侣：再加我们自己的 companion 场景集。
