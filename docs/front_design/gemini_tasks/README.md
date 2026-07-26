# Gemini Frontend Tasks

Run Gemini from `/home/wz`, not the project directory, so the global Gemini CLI configuration remains active:

当前执行任务：`03_static_experience_prototype.md`。

```bash
cd /home/wz
gemini --approval-mode=yolo --output-format=text \
  -p "$(cat /home/wz/luminous/docs/front_design/gemini_tasks/03_static_experience_prototype.md)"
```

Gemini outputs are reviewed against the design and backend contracts before acceptance.

新 agent 开始前先阅读 `docs/front_design/FRONTEND_AGENT_HANDOFF.md`。

后续涉及后端联通的 Gemini 任务只需阅读 `docs/front_design/frontend_api_contract_v1.md`；不需要翻阅 Python 后端实现。

所有视觉任务还应阅读 `docs/front_design/frontend_design_guidelines.md`。
