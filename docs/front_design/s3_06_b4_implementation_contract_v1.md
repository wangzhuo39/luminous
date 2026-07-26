# Luminous S3 B4：Task / Routine 实现契约

> 状态：实现基线 v1
> 日期：2026-07-26
> 设计输入：`s3_02_tasks_routines_design_v1.md`、`s3_05_implementation_plan_v1.md`
> Gemini Task trace：`/home/wz/gemini-api-traces/runs/20260726T020637.358699Z_luminous-s3-b4-task-contract_d12a0da9/`
> Gemini Routine trace：`/home/wz/gemini-api-traces/runs/20260726T020955.049939Z_luminous-s3-b4-routine-contract-retry_f52be874/`
> 工程校正：Codex 按当前 DataSource、adapter 与后端实现复核

## 1. 目标与边界

B4 在已有 `#today-overlay` 内完整实现：

- Task list/detail/create/edit、Step add/toggle、合法状态转换和原位归档确认；
- Routine list/detail/create/edit、会话内今日 check-in 和原位停用确认；
- 保守写入、草稿精确恢复、局部错误、双击防重、Abort/stale 丢弃；
- 桌面、390×844 软键盘、焦点/滚动恢复与 reduced-motion。

本批不新增页面、URL route、第二个 dialog 或框架；不实现 Activity、Diary、Reminder、Calendar、Action。

## 2. 单 dialog 导航

`lifeFlow.view` 扩展为有限集合：

```text
today | timeline |
tasks | task-detail | task-create | task-edit |
routines | routine-detail | routine-create | routine-edit
```

规则：

1. 所有 panel 互斥，关闭整个 dialog 后重置为 `today`；
2. 进入 detail 时聚焦返回按钮，进入 create/edit 时聚焦首个输入；
3. 返回上下文（触发 DOM node 与 `.today-scroll-area.scrollTop`）只保存在 View/Controller 闭包，不进入可序列化 AppState；
4. 返回后先 render，再恢复 scroll 和焦点；来源节点不存在时回退到对应列表入口；
5. Escape 仍由原生 dialog 关闭，不在子视图中改写成“返回”；
6. opaque key 可以存在于安全 AppState 和 Controller 闭包，但不得进入 DOM id、文本、tooltip、aria-* 或 data-*；DOM 事件只使用有限 action 和当前渲染 index。

## 3. AppState 契约

AbortController、operation token 和 DOM node 不进入 AppState，全部留在 Controller 闭包。

```text
lifeFlow.tasks
  status: unloaded|loading|ready|refreshing|error
  items: TaskVM[]
  error: SafeError|null
  selectedIndex: integer|null
  editor:
    mode: null|create|edit
    draft: { title, description, dueAt, priority }
    snapshot: same|null
    status: idle|pending|error
    error: SafeError|null
  action:
    kind: null|transition|archive|add-step
    status: idle|pending|error
    error: SafeError|null
    confirmingArchive: boolean
  stepDraft: string
  stepWrites: [{ index, status: pending|error, error }]

lifeFlow.routines
  status: unloaded|loading|ready|refreshing|error
  items: RoutineVM[]
  error: SafeError|null
  selectedIndex: integer|null
  editor:
    mode: null|create|edit
    draft: { title, schedule, reminderPolicy, active }
    snapshot: same|null
    status: idle|pending|error
    error: SafeError|null
  action:
    kind: null|checkin|deactivate
    status: idle|pending|error
    error: SafeError|null
    confirmingDeactivate: boolean
```

`TaskVM` 沿用 adapter 白名单：`key/title/description/status/dueAt/priority/steps`。`RoutineVM` 沿用 `key/title/schedule/active/reminderPolicy`，并在 AppState 安全复制时增加会话派生的 `checkinStatus: none|pending|completed|skipped|unknown`，初始为 `none`。

当前 `GET /api/routines` 不返回当日 check-in，前端不能在刷新后虚构“已照看”。B4 只在本次会话成功 check-in 后显示 `completed`；后端对同一 `(routine_id, period_key)` 使用唯一约束和 upsert，重复调用具备幂等兜底。该契约缺口留待 B9/后端 DTO 评估。

## 4. DataSource 精确映射

| 操作 | 当前真实调用 |
| --- | --- |
| Task list | `loadTasks({ status?, limit, signal })` |
| Task create | `createTask({ input, signal })` |
| Task edit | `updateTask({ key, changes, signal })` |
| Step add | `addTaskStep({ taskKey, input, signal })` |
| Step toggle | `updateTaskStep({ taskKey, stepKey, changes:{status}, signal })` |
| Task transition | `transitionTask({ key, action, input:{}, signal })` |
| Task archive | `archiveTask({ key, signal })` |
| Routine list | `loadRoutines({ activeOnly:false, limit, signal })` |
| Routine create | `createRoutine({ input, signal })` |
| Routine edit | `updateRoutine({ key, changes, signal })` |
| Routine check-in | `checkinRoutine({ key, input:{}, signal })` |
| Routine deactivate | `deactivateRoutine({ key, signal })` |

禁止使用 Gemini 草案中的 `payload` 参数或向 check-in 传 `date`。`/checkins` path 已由 DataSource 封装，View 不知道 HTTP path。

## 5. 保守写入规则

1. begin 前验证有限字段；失败只产生本地 validation 错误，不发请求；
2. begin 时复制当前 draft 到 snapshot，状态变 `pending`；input/textarea `readOnly`，select/提交与冲突动作 `disabled`；
3. 同域 operation gate 已占用时直接返回 `false`，快速双击不新增请求；
4. success 只有当前 token 可以落库；用 adapter 返回的完整安全 VM 替换/插入稳定列表，再清理 snapshot；
5. error 只有当前 token 可以写入 SafeError，并逐字段恢复 snapshot；不显示后端正文；
6. cancelled/stale 静默丢弃，不覆盖稳定状态；关闭 dialog/destroy 时 abort；
7. Step write 每个 index 独立 gate，只锁定对应 `aria-pressed` 按钮；
8. 归档/停用第一次点击只展开原位确认，第二次才请求；成功后保留 archived/inactive 只读详情并刷新 Today，避免突然丢失上下文；
9. Task/Routine 成功写入先更新对应稳定列表，再非阻塞刷新 Today；Today 刷新失败不回滚已确认的资源写入。

## 6. 文件职责与 DOM hooks

- `app-state.js`：安全 slice、有限迁移、draft snapshot 和稳定列表原子替换；不保存网络对象。
- `life-flow-controller.js`：扩展现有 controller，维护 load/write/step gates、AbortController、DataSource 调用、成功后 Today refresh；不新增 task/routine controller。
- `today-view.js`：Today item 对 task/routine 渲染真实按钮；只在闭包登记 index→安全 VM 与返回焦点上下文。
- `task-view.js`：纯 DOM render、事件委托、表单字段读取；不拼 HTTP、不持有稳定业务状态。
- `routine-view.js`：同上；不展示 streak、完成率或惩罚色。
- `main.js`：只收集 hooks、创建两个 View，并把事件委托到现有 controller；不增加业务分支。
- `index.html`：在 `.today-scroll-area` 增加互斥 Task/Routine panels 与真实 form fallback 骨架。
- `life-flow.css`：沿用 Today 材质；Task detail header 可在内部滚动容器吸顶，但不得再次叠加近黑面板；键盘可见时动作条进入文档流。

Hook 命名：

```text
resource-nav, tasks-open, routines-open
task-panel, task-back, task-list, task-list-state, task-create
task-form, task-title, task-description, task-due-at, task-priority
task-submit, task-cancel-edit, task-detail, task-step-list, task-step-form
task-step-title, task-status-actions, task-archive, task-confirmation, task-error
routine-panel, routine-back, routine-list, routine-list-state, routine-create
routine-form, routine-title, routine-schedule, routine-reminder-policy
routine-submit, routine-cancel-edit, routine-detail, routine-checkin
routine-deactivate, routine-confirmation, routine-error
```

动态 item 不写 key；允许 `data-item-index`、`data-step-index` 和有限 `data-action`。

## 7. 代码生成批次

1. **B4.1 共用状态合同（顺序前置）**：`app-state.js` + Node tests；目标 160–220 行增量。
2. **B4.2 Task View（可与 B4.3 并行）**：`task-view.js`；输入 B4.1 完整导出契约、当前 DOM/CSS；目标 160–210 行。
3. **B4.3 Routine View（可与 B4.2 并行）**：`routine-view.js`；目标 130–180 行。
4. **B4.4 Markup/CSS（可分两个并行调用）**：`index.html` 局部骨架与 `life-flow.css` B4 增量；每份不超过约 180 行。
5. **B4.5 Controller/Main 集成（顺序）**：扩展现有 controller/main/today-view，基于 B4.1–B4.4 当前真实源码；分 Task 和 Routine 两次中型调用，Codex 合并。
6. **B4.6 Tests/Browser（顺序）**：Node 状态/控制器测试与 Playwright browser harness；不让单次模型生成完整 13 项大文件。

每次调用附加真实文件内容并要求唯一结束标记；稳定输出目标仍为 4.5–7KB。

## 8. 验收矩阵

必须覆盖 Design 02 的 13 项：所有 Task 状态动作、archived/unknown 只读、移动 create/edit 键盘、validation/pending/error/success、draft 精确恢复、Step 局部隔离、Routine checked/error/inactive、双击单请求、stale、归档/停用与 Today 更新、长文本无溢出、键盘/焦点/44px/reduced-motion、DOM/AppState/日志拒绝字段。

最低截图：desktop task detail、desktop routine detail/checked、mobile task editor keyboard、task write error、routine check-in error。最终 B9 仍会做跨资源总验收。
