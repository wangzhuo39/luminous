# Luminous S3 Design 03：活动时间晶体与日记光影回响

> 状态：实现基线 v1
> 设计：Gemini；工程边界与完整性审查：Codex
> 初稿 trace：`/home/wz/gemini-api-traces/runs/20260725T021523.432944Z_luminous-s3-design03-activities-diary_906f322f/`
> 修订 trace：`/home/wz/gemini-api-traces/runs/20260725T022124.108473Z_luminous-s3-design03-repair_59f53bfb/`

## 1. 设计意图

- Activity 是“共同度过的时间晶体”，表达一起投入某件事，不做效率计时器。
- Diary 是“沉淀的光影回响”；生成草稿只是可编辑提议，保存权始终属于用户。
- 状态使用材料、色温和低频呼吸表达，不使用 KPI、倒计时、进度环、toast 或通用 spinner。
- 所有入口、列表、详情、编辑和确认都留在既有 Today dialog 中，不新增路由、页面或第二个 modal。

## 2. Today 内导航

层级固定为：

```text
Today 主视图
  ├─ Activity 列表 ─ Activity 会话/详情/创建
  └─ Diary 列表 ─ Diary 详情/编辑器
```

- 子视图沿用 `SubviewHeader`，包含 44×44 返回按钮、`<h2>` 和关闭按钮。
- 进入列表/详情时焦点落到返回按钮；进入创建/编辑时落到首个字段。
- 返回列表后恢复原滚动位置与触发项焦点；关闭 dialog 后焦点回 Today 入口。
- 删除确认是当前详情中的 `InlineConfirmation`，不是新 dialog。

## 3. 概念组件

- `ActivityList` / `ActivityItem`：活动集合和真实按钮列表项。
- `ActivitySessionView`：planned、active、paused 的状态操作视图。
- `ActivityDetailView`：终结状态的只读视图。
- `ActivityEditor`：标题和类型表单。
- `DiaryList` / `DiaryItem`：日记集合和列表项。
- `DiaryDetailView`：已保存/草稿详情。
- `DiaryEditor`：手动创建、已保存编辑和生成草稿共用的表单。
- `InlineConfirmation`：在原视图内确认日记移出。
- `LocalStatePanel` / `InlineErrorRegion`：局部加载、空、错误和重试。

## 4. Activity 视图与视觉语言

Activity 列表显示有限的 title、kind 和 status。kind 使用抽象几何刻痕或低显著性文本，不采用具象身份/审判图标。终结态使用较低对比度，但正文仍满足可读性要求。

会话视图以标题为中心，状态和操作围绕一枚静态或低频呼吸的“时间晶体”排列：

- planned：透明、边缘未闭合；
- active：冰蓝边缘聚拢，不超过 5 秒一次呼吸；
- paused：月雾灰，低频平缓起伏；
- completed：静态凝结；
- cancelled / expired：低亮度静态材料，不使用失败红。

契约没有可靠 duration、elapsed 或 progress，因此禁止计时器、秒数、进度环、预计完成时间和本地伪计时。

## 5. Activity 精确状态机

| 当前状态 | 可用按钮与请求 | 结果 |
| --- | --- | --- |
| `planned` | 开始 `POST …/start`；取消 `POST …/cancel` | active / cancelled |
| `active` | 暂停 `…/pause`；完成 `…/complete`；取消 `…/cancel` | paused / completed / cancelled |
| `paused` | 继续 `…/resume`；完成 `…/complete`；取消 `…/cancel` | active / completed / cancelled |
| `completed` / `cancelled` / `expired` | 无动作 | 只读 |
| `unknown` | 无动作 | 安全只读降级 |

- `expired` 是可显示终结态，但当前 HTTP 没有用户触发的 expire 动作。
- 当前 HTTP 没有 Activity DELETE；不得渲染删除、归档或伪撤销控件。
- 转换成功后只接受与当前 attempt token 匹配的服务端 ActivityVM。

创建只收集：

- title：必填、定长纯文本；
- kind：`focus | checkin | planning | reflection`。

`POST /api/activities` 成功后进入服务端返回活动的 planned 会话视图。不得提交计划时长等后端未可靠支持的字段。

## 6. Activity 对主场景的影响

主场景影响是前端派生的材料状态，不新增 API 字段：

- 初次 `GET /api/today` 只能证明 `active_activities`；可据此让主体光晕更稳定、聚焦。
- paused 只有在 Activity 子视图成功执行 `GET /api/activities`，或本次会话 pause 成功后才是已知事实。
- 从子视图返回主场景时可沿用内存中已知的 paused 状态，刷新页面后不得假装仍知道 paused。
- 不因补全该视觉状态增加轮询；未知时回退为 S2 的普通环境状态。
- kind 色调只做克制差异；不得覆盖 presence、offline、error 等更高优先级环境状态。

## 7. Diary 视图

- 列表按 date 降序，显示 title 与格式化 `<time>`；默认不显示 `status=deleted`。
- 详情只读展示 title、date 和 body，长文本自然换行。
- 编辑器使用真实 `<form>`、`<input>`、`<textarea>`；正文像一片融入温室的低反光纸面，不做浮夸拟物。
- 生成内容直接淡入，不使用打字机动画。
- 不提供 tags，因为当前后端不支持可靠标签写入。

## 8. Diary 持久化流程

### 8.1 手动创建

1. 用户输入非空 title 和 body。
2. 前端在提交时生成用户本地当天 `YYYY-MM-DD`，发送：

```text
POST /api/diary-entries
{ date, title, body, status: "saved" }
```

3. title 为空时保留焦点并显示局部校验，不静默代填“无题”。
4. 成功后使用响应中的 `diary_entry` 进入只读详情；后续编辑使用 PATCH。

### 8.2 生成草稿

1. “生成今日回顾”调用 `POST /api/diary-entries/draft`，可提交本地 date。
2. 返回对象已经持久化；adapter 同时兼容契约的 `entry` 和当前实现的 `diary_entry` 包装。
3. 必须捕获其 `entry_id` 为不透明 `key`，加载 title/body/date/status 到编辑器。
4. 用户保存时调用 `PATCH /api/diary-entries/{entry_id}`，提交修改字段并设置 `status: "saved"`。
5. 严禁为生成草稿再次执行普通 POST，否则会产生重复日记。

### 8.3 编辑已存在日记

- 已有 key 的日记始终 PATCH，只发送允许变化的 date/title/body/status 字段。
- 保存成功后以响应对象替换本地对象；不根据请求内容提前宣告成功。

### 8.4 移出日记

当前 DELETE 实际把服务端状态设为 `deleted`，不是物理删除。当前也没有恢复端点，因此 UI 同时避免“永久删除”和“可以恢复”的承诺。

内联确认文案：

- 标题：“从时间流中移出这篇日记？”
- 正文：“移出后，它将不再出现在当前日记列表中。”
- 操作：“确认移出” / “保留”。

确认后调用 `DELETE /api/diary-entries/{entry_id}`；仅服务端返回 `status=deleted` 后从默认列表移除并返回列表。

## 9. 安全 ViewModel

```text
ActivityVM
  key: opaque in-memory request key derived from session_id
  kind: focus | checkin | planning | reflection | unknown
  title: bounded plain text
  status: planned | active | paused | completed | cancelled | expired | unknown
  startedAt: valid timestamp | null
  endedAt: valid timestamp | null
  summary: bounded plain text | null

DiaryEntryVM
  key: opaque in-memory request key derived from entry_id
  date: valid YYYY-MM-DD | null
  title: bounded plain text
  body: bounded plain text
  status: draft | saved | deleted | unknown
  updatedAt: valid timestamp | null
```

Adapter 规则：

- 后端 ID 只映射为内存 key，用于请求路径寻址；不进入用户可见文本、console、错误信息或 `data-*` 属性。
- 不把 `task_id`、`content_ref`、metadata、user_scope、source_event_ids、created_at 或未知字段交给视图。
- 包装键只允许已知的 `activity`、`diary_entry` / `entry` 和 `items`；字段类型错误时失败关闭。
- 空时间映射 null；未知枚举映射 unknown 并只读降级。
- 所有文本用 `textContent` 或表单 value 渲染，不进入 `innerHTML`。

## 10. 写入与并发规则

所有 Activity 转换和 Diary CUD 使用同一保守状态机：

```text
idle → pending → success | error
```

- pending 创建唯一 attempt token 和 AbortController。
- 文本字段设为 `readOnly`，select 和相关动作按钮设为 `disabled`；不要对整个 form 使用 `pointer-events:none`。
- 关闭或替换子视图时 abort；abort 与过时响应都不展示错误、也不修改 AppState。
- 只有 token 匹配的成功响应能提交状态。
- 失败恢复提交前精确 draft、选择值、焦点可达性与动作能力；局部 `aria-live="polite"` 提供安全错误和重试。
- 不做 optimistic title/status/body 更新，不显示 toast。

## 11. 加载、空和错误

- 首次列表加载用 2–3 个静态材料占位或低频呼吸光，不使用 spinner。
- Activity 空态：“还没有共同度过的活动”；提供真实“计划一次活动”按钮。
- Diary 空态：“今天的思绪，也可以在这里安放”；提供“写一篇”按钮。
- 列表错误留在当前子视图，显示短错误与真实“重试”按钮。
- 写入错误不替换整个列表，只在操作附近显示。
- 文案不声称数据仅在本地、已加密、位于云端或会随账号同步；可用事实性文案“保存到 Luminous”。

## 12. 响应式、键盘与减弱动态

- 桌面沿用 420px Today 面板；移动端沿用不超过 85dvh 的 bottom sheet。
- 移动软键盘出现时编辑主体可滚动，保存动作进入普通文档流，聚焦字段和提交按钮都能滚入视口。
- 触控目标至少 44×44；状态不只依赖颜色；焦点环保持可见。
- Escape 关闭整个 dialog；返回按钮只退一级，不篡改浏览器历史。
- `prefers-reduced-motion: reduce` 下取消循环、位移和缩放，只允许瞬时变化或短淡入。

## 13. 截图与自动化验收

截图至少覆盖：

| 场景 | 桌面 | 移动 |
| --- | --- | --- |
| Activity 列表 | populated / empty / error | populated |
| Activity 会话 | planned / active / paused | active |
| Activity 终结详情 | completed / cancelled | completed |
| Activity 创建 | 默认 / pending / error | 软键盘 |
| Diary 列表 | populated / empty / error | populated |
| Diary 编辑 | 手动 / generated draft / pending / error | 长正文与软键盘 |
| Diary 详情与移出 | 只读 / 内联确认 | 内联确认 |
| 降级与动效 | unknown / reduced motion | reduced motion |

自动化必须断言：

1. Activity 每种状态只出现合法转换按钮，且没有 timer、progress、delete。
2. 手动 Diary POST 包含合法本地 date、非空 title、body 和 saved status。
3. 生成草稿保存只发送 PATCH 到返回 key 对应路径，不发送第二个 POST。
4. Diary DELETE 响应为 deleted 后才从列表移除；确认文案不含永久/不可撤销/可恢复承诺。
5. `/api/today` 未提供 paused 时主场景不虚构 paused；打开活动列表或成功 pause 后才可派生。
6. 后端 session_id/entry_id 不出现在用户文本、console 或 DOM 属性中。
7. pending 时 input/textarea readOnly、select/button disabled；失败精确恢复；过时响应无效。
8. 长文本、键盘导航、44×44 触控、焦点返回、软键盘和 reduced motion 均通过浏览器验收。
9. 页面不存在 tags、Activity DELETE、通用 spinner、toast、计时器和无依据隐私声明。

## 14. 工程门控

- Activity DELETE：当前 HTTP 未实现，门控。
- Diary tags：当前领域模型未实现，门控。
- paused 初始主场景影响：`/api/today` 未提供，只有在活动集合被明确加载后才启用。
- 恢复 deleted Diary：当前无恢复 API，不设计控件。
- Companion 主动提议活动/日记：归入后续 action preview/confirm 设计，不在本文定义。
