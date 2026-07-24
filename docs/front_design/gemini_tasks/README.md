# Gemini Frontend Tasks

Run Gemini from `/home/wz`, not the project directory, so the global Gemini CLI configuration remains active:

当前执行任务：`02_phase1_companion_scene.md`。

```bash
cd /home/wz
gemini --approval-mode=yolo --output-format=text \
  -p "$(cat /home/wz/luminous/docs/front_design/gemini_tasks/02_phase1_companion_scene.md)"
```

`01_full_frontend_rebuild.md` 是已废弃的全量重构任务，不应再执行。

Gemini outputs are reviewed against the design and backend contracts before acceptance.
