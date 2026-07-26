# Luminous S3 Design 02：任务晶体与习惯露珠

> 状态：实现基线 v1
> 设计：Gemini；工程边界与完整性审查：Codex
> 初稿 trace：`/home/wz/gemini-api-traces/runs/20260725T020943.622256Z_luminous-s3-design02-tasks-routines_b8e5e692/`
> 修订 trace：`/home/wz/gemini-api-traces/runs/20260725T021124.283370Z_luminous-s3-design02-tasks-routines-repair_b26609e3/`
> 视觉补充 trace：`/home/wz/gemini-api-traces/runs/20260725T021244.955029Z_luminous-s3-design02-visual-supplement_25f953e0/`

## 1. 设计意图

- Task 是“凝结的晶体”，具有确定的生长状态；归档是移入基座，不是销毁。
- Routine 是“叶片上的露珠”；停用是不再承接今日晨露，过去记录仍存在。
- 写入是“光影注入”，只有服务端确认后才落定；失败保留用户雕琢的原文。
- 状态不使用红色、橙色、羞辱或断签惩罚。

## 2. Today 内导航

- 所有详情、创建、编辑和确认都在 `#today-overlay` 内完成，不打开第二个 dialog。
- Today 主视图与子视图互斥显示；子视图具有真实 44×44 返回按钮。
- 进入详情时焦点落到返回按钮；进入创建时落到首个输入。
- 返回后恢复主列表滚动位置并把焦点还给原 TodayItem 按钮。
- 关闭整个 dialog 后再次打开默认回到 Today 主视图。

## 3. 概念组件

- `SubviewHeader`：返回、标题、关闭。
- `TaskDetail` / `TaskEditor`：只读详情和真实 `<form>`。
- `TaskStepList`：每个步骤使用 `<button aria-pressed>`，不使用 checkbox 外观。
- `TaskStatusControls`：只展示当前状态允许的动作。
- `RoutineDetail` / `RoutineEditor`：轻量习惯详情和表单。
- `RoutineCheckInButton`：今日一次打卡，pending 防重。
- `InlineConfirmation`：归档/停用在原位置二次确认，无新 modal。
- `LocalWriteState`：idle/pending/error 的局部材料变化。
- `InlineErrorRegion`：短 `aria-live="polite"`，只播报本次操作。

## 4. Task 表单与布局

字段：

- title：必填单行纯文本；
- description：可选 textarea；
- dueAt：合法 ISO 日期时间或 null；
- priority：`low | normal | high`；
- steps：安全有序列表。

桌面 420px 面板：sticky header；可滚动主体；标题、due/priority、description、steps 垂直分组；动作条保持可发现但不得遮住最后一个字段。移动端 85dvh 改为单列，软键盘出现后动作条进入普通文档流，所有字段和提交按钮可滚入视口。

步骤完成按钮：

- 未完成：虚线圆环与可见“标记完成”；
- 已完成：实心晶体与可见“标记待处理”；
- pending：只锁定该步骤按钮；
- error：只在该步骤下显示安全错误，其他步骤仍可操作。

## 5. Task 有限状态

| 当前状态 | 可用动作 |
| --- | --- |
| `open` | start、block、complete、cancel、archive |
| `in_progress` | block、complete、cancel、archive |
| `blocked` | start（进入 in_progress）、complete、cancel、archive；如提供回 open 必须显式 PATCH |
| `completed` / `cancelled` | archive |
| `archived` | 只读，无流转控件 |
| `unknown` | 安全只读降级，不显示动作 |

- “归档任务”调用 DELETE，服务端把状态改为 archived；不得称为删除/粉碎。
- 当前无 restore/undo 端点，UI 不提供虚假撤销。
- blocked 使用“暂时搁置”；恢复动作显示“继续进行”，不用警告图标。

## 6. Routine 表单与布局

字段：

- title：必填；
- schedule：仅 `daily | weekly`；
- reminderPolicy：仅 `none | remind`；
- active：boolean。

详情以标题、每日/每周文本和一个中心 Check-in 区为主，不显示 streak KPI：

- unchecked：月光灰“照看今天”；
- pending：按钮锁定、静态或 5s 低频微光；
- checked：冰蓝静态“今日已照看”，不再提交；
- error：按钮恢复，草稿/稳定状态不变，局部重试；
- inactive：只读说明与重新编辑入口，不出现今日打卡。

“停用习惯”调用 DELETE 或 PATCH `active:false`，实际语义是停止在 Today 出现，不是永久删除。确认在同一子视图原位完成。

## 7. 写入状态机

每个资源/操作保存唯一 attempt token 与 AbortController：

```text
idle -> pending -> success
                -> error -> idle/new pending
                -> cancelled -> idle
```

- begin 时冻结当前可见 draft snapshot；重复提交直接忽略。
- pending 时文本 input/textarea 为 `readOnly`，仍可阅读/选择；select 和动作/提交按钮 disabled。禁止给整个 form `pointer-events:none`。
- success 只接受当前 token 的有效响应；更新稳定 ViewModel 后返回/保留详情，并恢复焦点。
- error 恢复精确 draft、解锁编辑、显示有限 AppError 文案。
- retry 读取当前可见表单值，创建新 token；禁止静默重放用户编辑前的隐藏 payload。
- 组件销毁/关闭时 abort；被取消或过期响应不得更新 AppState/DOM。

## 8. 安全 ViewModel

```text
TaskVM
  key: opaque in-memory key
  title: bounded plain text
  description: bounded plain text | null
  status: open|in_progress|blocked|completed|cancelled|archived|unknown
  priority: low|normal|high
  dueAt: valid date | null
  steps: [{ key, title, status: open|completed|cancelled|unknown }]

RoutineVM
  key: opaque in-memory key
  title: bounded plain text
  schedule: daily|weekly|unknown
  reminderPolicy: none|remind|unknown
  isActive: boolean
  checkinStatus: pending|completed|skipped|none|unknown
```

- 原始 resource ID 只在 adapter/controller 的内存映射中用于 API 路径，不进入可见文本、DOM id、tooltip 或日志。
- HTML、Markdown、metadata、user_scope、raw period_key 与未知嵌套结构拒绝。
- 未知 status 映射为 `unknown`，安全项目仍可只读展示。
- Routine streak 不进入普通 Today 视觉。

## 9. AppError、验证与重试

- 网络/超时/服务不可用等使用共享有限 AppError presentation map，不显示后端正文。
- 当前后端没有 409 并发协议，不新增可见 `conflict` 类；未知异常降级为安全 unknown/server 文案。
- 字段验证可指出“标题”等用户可修正字段，但不能引用后端错误字符串。
- `aria-describedby` 把字段错误关联到对应 input；提交失败的通用错误位于动作条上方。
- error 后首焦点落到第一个无效字段或重试按钮；不强制抢走用户正在编辑的焦点。

## 10. 视觉参数

- 继承 Today 的 `rgba(10,12,16,0.65)` 材质和最终截图确定的 blur。
- 分组间距约 20px、控件间距 8–12px、内容 padding 24px。
- 输入底线 `1px solid rgba(255,255,255,0.15)`；focus 使用克制冰蓝。
- low 为月光灰、normal 为 80% 白、high 为冰蓝微光；绝不使用红橙 urgency。
- 所有按钮至少 44×44；正文 0.95rem，label 0.85rem。
- Reduced Motion 下子视图瞬时/极短淡入，pending 保留静态明度变化，无循环动画。

## 11. 反模式和文案

- 无 card wall、kanban、checkbox 墙、完成率、streak、进度条、Toast、Banner、Spinner、粒子或滑动唯一操作。
- 不用隐喻掩盖结果：可见标签必须写“归档任务”“停用习惯”“暂时搁置”“继续进行”。隐喻只作辅助说明。
- 不显示“永久删除”或提供不存在的撤销。
- ordinary user CRUD 在子视图内直接确认；不错误调用 companion preview/confirm。

## 12. 浏览器与截图验收

必须覆盖：

1. 桌面 task detail：open/in_progress/blocked/completed/cancelled/archived/unknown 的准确控件集合。
2. archived 与 unknown：只读、无动作、结果文案明确。
3. 390×844 task create/edit：模拟软键盘，标题/描述/动作均可达。
4. 表单 validation/pending/error/success：readOnly 与 disabled 分工正确。
5. 精确 draft 恢复：长描述提交失败后字节等价保留。
6. step open/completed/pending/error：局部锁定与错误不影响其他步骤。
7. routine unchecked/pending/checked/error/inactive：无 streak 与惩罚色。
8. 快速双击：一个网络请求；同一 pending 不重复。
9. stale response：旧 token 返回不覆盖新稳定状态。
10. 归档/停用：可见文本准确、确认原位、成功后 Today 更新。
11. 超长中文和无空格英文：无水平溢出。
12. Tab/Enter/Escape、focus entry/return、44px 热区和 reduced-motion。
13. DOM/AppState/日志不含拒绝字段或原始错误。

## 13. 移交后续设计

- Activity 与 Diary 的场景/表单；
- Reminder 与 Calendar 的详情/创建/编辑；
- companion action preview/confirm；
- S3 跨域缓存、refresh、批次和最终验收合同。
