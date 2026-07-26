# Luminous S3 B5：Activity 实现契约 v1

状态：可实施
范围：Activity 列表、创建、会话详情与合法状态转换；Diary 属于 B6。

## 1. 产品与视觉目标

Activity 是 Today 内的一枚“时间晶体”，不是计时工具。列表负责找到活动；详情以晶体材质表达状态；创建只收集服务端已可靠支持的字段。视觉必须延续“晶格温室”：冷白与冰蓝折射、克制的空间纵深、非身份化几何刻痕、低频或静态动效。

禁止计时器、秒数、进度环、预计完成时间、Activity 删除/归档、toast，以及无依据的本地/加密/云同步承诺。

## 2. 页面与 DOM 接缝

Today 主面板的生活流导航增加“活动”。新增一个 `activity-panel`，复用同一 dialog 和滚动容器，不新增顶层 overlay。

Activity 子视图只有：

- `activities`：列表、加载/空/错误、创建入口；
- `activity-detail`：标题、kind、status、可选起止时间与 summary、合法动作；
- `activity-create`：title 与 kind 表单。

稳定 hook：`activities-open`、`activity-panel`、`activity-back`、`activity-list-state`、`activity-list`、`activity-create`、`activity-detail`、`activity-crystal`、`activity-status-actions`、`activity-form`、`activity-title`、`activity-kind`、`activity-submit`、`activity-cancel-edit`、`activity-error`。

不把 Activity key 写入文本、`id`、class 或任何 `data-*`；列表选择只分发内存 index。

## 3. 安全状态模型

`lifeFlow.activities` 沿用资源状态骨架：

- 加载：`unloaded | loading | refreshing | ready | error`；
- `items: ActivityVM[]` 与 `selectedIndex`；
- 创建编辑器：`mode: null | create`、`draft: { title, kind }`、snapshot、pending/error；
- 动作：`kind: transition`、pending/error。

ActivityVM 只含：`key`、`kind`、`title`、`status`、`startedAt`、`endedAt`、`summary`。未知 kind/status 映射为 `unknown`；未知状态只读。

## 4. 请求契约

- 列表：`GET /api/activities?limit=100`；
- 创建：`POST /api/activities`，body 仅 `{ title, kind }`；
- 转换：`POST /api/activities/{opaque-key}/{action}`，body `{}`；
- action 仅 `start | pause | resume | complete | cancel`。

合法转换：

| 当前状态 | action |
| --- | --- |
| planned | start, cancel |
| active | pause, complete, cancel |
| paused | resume, complete, cancel |
| completed / cancelled / expired / unknown | 无 |

AppState 在写入开始前按服务端返回的当前状态再次校验。fixture adapter 同样拒绝非法转换，避免测试环境生成现实中不存在的状态。

## 5. 并发、失败与离线

- 每次加载/写入使用唯一 operation token 与 AbortController；
- 同一资源写入期间拒绝加载和第二次写入；关闭 Today、切换/替换子视图或离线时 abort；
- 过时响应不修改 AppState、不报错；
- 创建 pending 时 input 为 readOnly、select 与相关按钮 disabled；动作 pending 时全部状态动作 disabled；
- 不乐观更新标题或状态；只用 token 匹配的服务端 ActivityVM 替换当前项；
- 创建失败精确恢复 title/kind draft；动作失败保留原服务端状态与合法动作，在操作附近显示安全错误。

## 6. 主场景派生

- Today 首次响应只允许从 `activeActivities` 推导 `active`；
- `paused` 只能由成功加载的 Activity 列表或本次会话 pause 成功得知；
- 返回主场景后可沿用内存事实，刷新页面不能伪造 paused；
- Activity 材料提示不得覆盖 offline/error/presence 等更高优先级环境状态；不增加轮询。

本批只建立 `data-activity-presence="active|paused|none"` 这类非敏感派生视觉状态，不暴露 key 或原始响应。

## 7. 无障碍与响应式

- 使用真实 button、form、input、select；列表项按钮触控目标不小于 44×44；
- 状态必须有中文文本，不能只依赖颜色/形状；局部错误使用 `aria-live="polite"`；
- 返回只退一级，Escape 仍关闭整个 Today dialog；
- 移动端沿用不超过 85dvh 的 bottom sheet，表单动作在普通文档流；
- reduced motion 下停止晶体呼吸、位移和缩放，只保留静态材料。

## 8. 验收门槛

1. planned、active、paused、completed/cancelled/expired/unknown 只显示合法动作；
2. 请求 path/body 精确，且页面不存在 timer、progress、delete/archive；
3. 加载、空、错误、创建 pending/error、动作 pending/error 可见且不会替换整个列表；
4. key 不出现在用户文本、console、DOM 属性；
5. pending 锁定、失败 draft 恢复、abort 和 stale response 均通过自动化；
6. Today 首次只推导 active，列表加载或 pause 成功后才可推导 paused；
7. 桌面、移动、键盘、焦点返回、reduced motion 与“晶格温室”视觉截图通过 Chromium 验收；
8. B1–B4 回归测试保持通过。
