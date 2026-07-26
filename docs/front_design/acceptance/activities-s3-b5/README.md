# S3 B5 Activity 验收记录

日期：2026-07-26
结论：通过，可进入 B6 Diary。

## 交付范围

- Today 同一 dialog 内新增 Activity 列表、创建与会话详情；
- `planned → active → paused → active → completed` 与 `planned → cancelled` 合法转换；
- completed/cancelled/expired/unknown 只读，页面无 Activity DELETE、archive、timer 或 progress；
- 创建只提交 `{ title, kind }`，转换只提交 `{}` 到精确 action path；
- pending single-flight、AbortController、stale response 拒绝、错误草稿精确恢复；
- Activity key 仅留在内存状态/闭包，不进入用户文本、console 或 DOM 属性；
- Today 初次只从 `active_activities` 推导 active；明确加载列表或本地 pause 成功后才推导 paused；
- “时间晶体”状态材料、390px 表单、软键盘普通文档流、44px 触控与 reduced-motion。

## 自动化证据

```text
node --test tests/frontend/*.test.mjs
tests 140
pass 140
fail 0

node tests/frontend/s3-b5-browser-acceptance.mjs
B5_BROWSER_ACCEPTANCE_OK scenarios=3 screenshots=8
```

全局回归同时通过：

```text
B4_BROWSER_ACCEPTANCE_OK scenarios=3 screenshots=6
B3_BROWSER_ACCEPTANCE_OK viewports=2 scenarios=2 screenshots=6
CRYSTAL_SOLARIUM_BROWSER_OK scenarios=3 screenshots=4
```

浏览器场景覆盖 fixture 完整生命周期、API 精确 path/body + 重复提交 + 安全错误、移动软键盘和 reduced-motion。截图：

- `desktop-activity-list.png`
- `desktop-activity-active.png`
- `desktop-activity-paused.png`
- `desktop-activity-completed.png`
- `desktop-activity-planned.png`
- `desktop-activity-cancelled.png`
- `mobile-activity-create-reduced-motion.png`
- `desktop-activity-api-error.png`

结构化结果见 `browser-acceptance.json`。

## Gemini 设计与复审

项目外完整 trace：

```text
/home/wz/gemini-api-traces/runs/20260726T035707.345390Z_luminous-b5-activity-visual-v1_e3d71ff1/
/home/wz/gemini-api-traces/runs/20260726T041058.607468Z_luminous-b5-activity-audit-v1_fec88953/
```

首个调用一次成功，贡献“晶体簇—居中时间晶体—凝露表单”视觉方向。其示例包含契约外 kind 和不符合可访问性的 pending CSS，未照抄；Codex 按真实 API 与状态机整合。

复审调用前两次失败、主端点第 3 次成功；Gemini 结论为“通过”、无 P0/P1，并明确允许进入 B6。成功 run 保留所有内部失败 attempt。复审后 Codex 又补齐 planned/cancelled 截图，并把 fixture 完成时间从早于开始修正为正确时序；这些不改变复审通过的视觉基线。

## 实施中发现并修正

1. `.activity-list { display:grid }` 会覆盖原生 `hidden` 表现，导致详情与列表叠层；已在 `life-flow.css` 加显式 hidden selector，并加入浏览器断言。
2. 既有软键盘 sticky 动作区会遮住 Activity 表单；Activity 专项覆盖为普通文档流，并断言提交按钮可滚入且获得焦点。
3. fixture 原来在 15:00 开始却以 12:00 完成；fixture clock 改为 16:00，避免验收数据自相矛盾。
4. planned 的虚线边缘在多边形裁切下不够明显；增加带缺口的内部折射线，并补 planned/cancelled 终态截图。
