# Luminous S3 B6：Diary 实现契约 v1

状态：可实施
范围：Diary 列表、手动创建、生成持久化草稿、编辑保存、只读详情与移出；Reminder/Calendar 属于 B7。

## 1. 产品与视觉目标

Diary 是融入晶格温室的“低反光纸面 / 光影回响”，不是博客后台或富文本 CMS。列表像被光尘标记的信笺索引，正文像温室玻璃内侧的一页安静纸面；生成内容直接出现，不做打字机、粒子或 toast。

不支持 tags、富文本、自动保存、版本恢复、永久删除承诺或“仅本地/已加密/云同步”等无依据声明。

## 2. 子视图与稳定 hooks

继续使用唯一 Today dialog：

- `diaries`：按 date 降序的列表、loading/empty/error、写一篇、生成今日回顾；
- `diary-detail`：title/date/body/status 的只读纸面、编辑与移出；
- `diary-create`：手动 title/body 表单；
- `diary-edit`：编辑已有 saved 或服务端已持久化 draft。

稳定 hook：`diaries-open`、`diary-panel`、`diary-back`、`diary-list-state`、`diary-list`、`diary-create`、`diary-generate`、`diary-detail`、`diary-edit`、`diary-remove`、`diary-confirmation`、`diary-form`、`diary-title`、`diary-body`、`diary-submit`、`diary-cancel-edit`、`diary-error`。

opaque entry key 只保存在 AppState/Controller/View 闭包，不写入文本或 DOM 属性；列表只分发内存 index。

## 3. 安全状态

`lifeFlow.diaries` 使用资源状态骨架：加载状态、`DiaryEntryVM[]`、`selectedIndex`、editor 与 action。

DiaryEntryVM 只含：`key`、`date`、`title`、`body`、`status`、`updatedAt`。status 仅 `draft | saved | deleted | unknown`；deleted 默认不进入列表，unknown 只读。

编辑 draft：`{ date, title, body, status }`。title/body 保留精确用户输入；提交时校验 title 与 body 均非空。页面不允许用户直接编辑 status。

## 4. 精确持久化流程

### 手动创建

提交时生成用户本地当天 `YYYY-MM-DD`：

```text
POST /api/diary-entries
{ date, title, body, status: "saved" }
```

成功后用响应进入只读详情。title 为空时保留草稿与可达焦点，禁止代填“无题”。

### 生成今日回顾

```text
POST /api/diary-entries/draft
{ date: localDate }
```

响应已经持久化。必须立即保存返回 key，将条目加入/替换列表，进入 `diary-edit` 并加载返回的 title/body/date/status。用户保存只允许：

```text
PATCH /api/diary-entries/{key}
{ date, title, body, status: "saved" }
```

严禁再执行普通 POST。

### 编辑与移出

已有 key 一律 PATCH。移出需要内联确认：

- “从时间流中移出这篇日记？”
- “移出后，它将不再出现在当前日记列表中。”
- “确认移出” / “保留”。

确认后 `DELETE /api/diary-entries/{key}`；只有响应 status 为 `deleted` 才从列表移除并回到 `diaries`。不得承诺永久删除、不可撤销或可以恢复。

## 5. 并发与失败

- list/create/generate/update/remove 使用 resource 单资源 gate、唯一 token 与 AbortController；
- pending 时 input/textarea `readOnly`，相关 button `disabled`，不用 `pointer-events:none`；
- 关闭 dialog、离线或替换操作时 abort；过时响应不修改状态、不显示错误；
- create/edit 失败恢复提交前精确 draft；generate 失败留在列表；remove 失败保留详情和确认上下文；
- 不乐观新增、保存或移出；局部 `aria-live=polite` 显示安全错误。

## 6. 排序、响应式与验收

- 默认过滤 deleted；有效 date 按降序，缺失 date/unknown 稳定放后；
- body 用 `textContent`，保留换行和自然换行；长正文不得横向溢出；
- 390px/软键盘时正文可滚动、操作区普通文档流、44px 触控；reduced-motion 静态；
- 自动化必须证明手动 POST body、draft→PATCH 无第二 POST、DELETE 等 deleted 后移除、失败恢复、重复提交、opaque key 不泄露；
- 截图覆盖 populated/empty/error、手动/生成编辑器、详情/移出确认、长正文移动端和 reduced-motion。
