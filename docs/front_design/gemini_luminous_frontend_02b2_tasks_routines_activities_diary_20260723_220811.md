# Batch 2B-2：共同任务、例行习惯、活动会话与日记回顾规格

## 1. 共同生活动作原则

在「晶格温室」的视觉与交互语境下，任务、习惯、活动和日记不是为了优化效率（Productivity），而是为了构建**陪伴感（Companionship）**和**生活锚点（Life Anchors）**。

*   **非效率导向（Anti-Dashboard）：** 拒绝使用强烈的红色警告、倒计时滴答声或压迫感的进度条。未完成的事项像温室里未开的花，等待浇灌，而不是逾期的债务。
*   **共同在场（Co-Presence）：** 活动（Activities）强调「正在一起做」的状态。开启活动时，界面呼吸感和虚拟伙伴的状态将同步改变，提供无声的陪伴。
*   **提议而非定性（Suggest, Don't Define）：** 日记回顾由系统生成草稿作为「一天的回声」，用户拥有绝对的修改权。系统不替用户总结人生的好坏，只提供柔软的记忆切片。
*   **确认与安全边界（Safe Boundaries）：** 涉及状态变更、记忆删除等重要操作，必须通过沉浸式的预览与确认（ActionPreviewConfirm）机制，确保用户控制权。

---

## 2. 组件规格：Task Controls / 共同任务

覆盖日常具体事项的创建、拆解（步骤）与流转。

*   **DOM 建议：**
    ```html
    <div class="task-card glass-panel" data-task-id="123" data-state="open">
      <div class="task-header">
        <button class="state-toggle icon-btn"></button>
        <span class="task-title" contenteditable="false">给植物浇水</span>
        <div class="task-actions">...</div>
      </div>
      <ul class="task-steps">
        <li class="step-item" data-step-id="1" data-state="open">...</li>
      </ul>
    </div>
    ```
*   **API 映射：**
    *   创建/获取：`POST /api/tasks`, `GET /api/tasks`
    *   修改/删除：`PATCH /api/tasks/{id}`, `DELETE /api/tasks/{id}`
    *   步骤管理：`POST /api/tasks/{id}/steps`, `PATCH /api/tasks/{id}/steps/{step_id}`
    *   状态流转：`POST /api/tasks/{id}/start|complete|block|cancel`
*   **交互与视觉细节：**
    *   **材质：** 基础状态为半透明磨砂玻璃（`backdrop-filter: blur(8px)`）。
    *   **状态流转动画：** 点击完成（Complete）时，复选框内不出现生硬的对勾，而是从中心晕开一抹温暖的亮光（Soft Glow），随后整个卡片透明度降低，文字呈现低对比度的柔和灰绿色。
    *   **阻塞（Blocked）：** 呈现为轻微的冷灰色覆盖（如温室玻璃上的水雾），文案提示变为「暂时搁置」。
    *   **步骤（Steps）：** 采用微型光点作为列表项符号，完成时光点点亮。
*   **移动端：** 卡片支持左右滑动呼出快捷操作（左滑 Complete，右滑 Block/Cancel），滑动过程伴随毛玻璃折射率变化的 CSS 滤镜效果。

---

## 3. 组件规格：Routine Controls / 例行习惯

处理每日/每周的重复性轻量承诺。

*   **API 映射：**
    *   管理：`GET/POST /api/routines`, `PATCH/DELETE /api/routines/{id}`
    *   打卡：`POST /api/routines/{id}/checkins`
*   **视觉与交互细节：**
    *   **形态：** 采用「露珠指示器」（Dewdrop Indicator）。每个 Routine 显示为一片叶子状的容器，过去几天的打卡记录显示为叶片上的露珠。
    *   **Check-in 动作：** 用户点击「今日打卡」时，一颗新的露珠滴落并融合，伴随清脆/水润的微交互反馈。
    *   **连续与错过（Streaks & Misses）：** 不使用「断签警告」。错过打卡的日子，露珠位仅留下一个淡淡的水痕轮廓（`opacity: 0.2`），不产生负罪感。
    *   **提醒策略：** 到达设定时间时，Routine 卡片边缘产生极其缓慢的呼吸光晕（Morning Mist Glow），而非弹窗打断。

---

## 4. 组件规格：Activity Session / 一起做

用于专注、阅读、冥想等需要持续一段时间的「陪伴会话」。

*   **API 映射：**
    *   管理：`GET/POST /api/activities`, `GET /api/activities/{id}`
    *   状态控制：`POST /api/activities/{id}/start|pause|resume|complete|cancel`
*   **视觉与交互细节：**
    *   **Active 状态与主场景联动：** 当 Activity 处于 `active` 状态时，主界面的背景光影会向用户的卡片区域聚拢。虚拟伙伴的状态（Presence）会自动更新为对应的陪伴文案（如：「正在和你一起阅读」）。
    *   **控制面板：** 极简的悬浮控制台（Floating Console）。包含柔和的计时器（无秒数跳动的焦虑感，仅显示分钟或进度环）和播放/暂停/结束按钮。
    *   **暂停（Paused）：** 进度环呈现脉冲式微光，提示会话挂起但未结束。
*   **移动端：** 活动进行时，即使折叠面板，屏幕边缘也会保留一条 2px 的动态光带，提示「陪伴正在进行」。

---

## 5. 组件规格：DiaryReview / 今日回顾

一天结束时的记忆整理与情绪回声。

*   **API 映射：**
    *   获取/提交：`GET/POST /api/diary-entries`
    *   修改/删除：`PATCH/DELETE /api/diary-entries/{id}`
    *   生成草稿：`POST /api/diary-entries/draft`
*   **视觉与交互细节：**
    *   **Timeline 片段：** 界面左侧展示今日完成的 Tasks、Routines 和 Activities 作为时间轴切片（半透明微缩卡片）。
    *   **Draft 呈现：** 点击「生成回顾」后，右侧展开一张具有宣纸质感的 UI 面板（`background: radial-gradient(circle, #fff, #f8f9fa)`）。AI 提取时间轴生成的文本以「打字机淡入」效果出现。
    *   **用户编辑：** 草稿文本区域完全可编辑（`contenteditable="true"` 或 `textarea` 伪装）。系统提示文案为：「这是我眼中的今天。你可以修改它，或者写下你真正的感受。」
    *   **隐私提示：** 保存按钮旁带有微小的锁图标，悬浮提示：「日记仅保存在本地与你的专属记忆库中」。

---

## 6. 组件规格：ActionPreviewConfirm / 行动确认

用于拦截高风险或不可逆操作（如删除长期 Routine、取消进行中的重要 Activity）。

*   **API 映射：**
    *   预览影响：`POST /api/actions/preview`
    *   确认执行：`POST /api/actions/confirm`
*   **视觉与交互细节：**
    *   **沉浸式遮罩：** 触发时，背景产生深度高斯模糊（`backdrop-filter: blur(20px) saturate(120%)`），将用户注意力完全聚焦于确认对话框。
    *   **Preview 信息：** 弹窗内清晰列出操作后果（例：「取消此活动将不会记录本次陪伴的 45 分钟」），数据由 preview API 提供。
    *   **交互确认：** 放弃传统的「确认/取消」双按钮，采用「长按注水」或「滑动确认」的交互，防止误触，增加仪式的重量感。取消或失败时，弹窗化为散落的光点消失。

---

## 7. 核心流程：创建共同任务并推进

1.  **创建：** 用户在输入框键入任务名并回车 -> UI 乐观更新生成 `task-open` 卡片 -> 调用 `POST /api/tasks` -> 响应成功，更新真实 ID。
2.  **拆解：** 用户点击卡片展开，输入子步骤 -> UI 显示 `step-open` -> 调用 `POST /api/tasks/{id}/steps`。
3.  **开始：** 用户点击「开始」 -> UI 状态变为 `task-in-progress`，卡片边框微亮 -> 调用 `POST /api/tasks/{id}/start`。
4.  **推进与完成：** 用户勾选所有子步骤 (`PATCH /api/tasks/{id}/steps/{step_id}`) -> 主卡片自动触发展开光晕动画，状态变为 `task-completed` -> 调用 `POST /api/tasks/{id}/complete`。

---

## 8. 核心流程：习惯打卡与活动会话

**习惯打卡：**
1.  **触发：** 到达设定时间，Routine 露珠槽亮起 (`routine-due`)。
2.  **Check-in：** 用户点击打卡 -> UI 播放露珠滴落动画，状态变更为 `routine-done` -> 调用 `POST /api/routines/{id}/checkins` -> 连续天数 +1。

**活动会话：**
1.  **准备：** 用户选择 Activity 并设定意图 -> UI 显示 `activity-planned`。
2.  **开始：** 用户点击启动 -> 界面进入专注模式，呼出悬浮控制台 (`activity-active`) -> 调用 `POST /api/activities/{id}/start`。
3.  **暂停/继续：** 过程中用户点击暂停 -> 进度环呼吸闪烁 (`activity-paused`) -> 调用 `POST /api/activities/{id}/pause`。
4.  **结束：** 倒计时结束或手动结束 -> 弹出 `ActionPreviewConfirm` 确认保存 -> 调用 `POST /api/activities/{id}/complete` -> 返回主场景，状态归档。

---

## 9. 核心流程：日记草稿与今日回顾

1.  **回顾触发：** 晚间时段，主界面出现「今日回声」入口。
2.  **生成草稿：** 用户点击 -> UI 进入 `diary-drafting` 状态（光晕流转的骨架屏） -> 调用 `POST /api/diary-entries/draft`。
3.  **草稿就绪：** API 返回 -> UI 呈现 `diary-draft-ready`，文本淡入。
4.  **编辑与保存：** 用户修改文本内容 -> 点击保存 -> UI 进入 `diary-saving`（图标变为加载光环） -> 调用 `POST /api/diary-entries` -> 成功后显示 `diary-done` 状态卡片。

---

## 10. 状态与错误矩阵

| 状态 ID | 视觉表现 (晶格温室风格) | 提示文案 / 状态 | 可操作项 |
| :--- | :--- | :--- | :--- |
| `task-open` | 基础磨砂玻璃，清晰文字 | 无 / 待办 | 编辑, 开始, 删除, 添加步骤 |
| `task-in-progress`| 边缘附带柔和的动态高光 | 「进行中」 | 完成, 阻塞, 取消 |
| `task-blocked` | 玻璃起雾效果，低对比度 | 「暂时搁置」 | 恢复(Start), 取消 |
| `task-completed` | 整体变透明，文字呈灰绿色 | 「已完成」 | 撤销(变回open) |
| `task-cancelled` | 极度透明，带有删除线 | 「已取消」 | 删除, 恢复 |
| `step-open` | 空心微型光点 | 无 | 标记完成 |
| `step-done` | 实心发光微型光点 | 无 | 撤销完成 |
| `routine-due` | 露珠槽缓慢呼吸闪烁 | 「等待打卡」 | 打卡(Check-in) |
| `routine-done` | 露珠槽填满并静止发光 | 「今日已完成」 | 撤销打卡 |
| `routine-missed` | 仅保留淡淡的水痕轮廓 | 无 / 未打卡 | 无 (不可补签，避免焦虑) |
| `activity-planned`| 静态活动卡片，准备状态 | 「计划中」 | 开始, 编辑, 删除 |
| `activity-active` | 悬浮控制台，全局呼吸边框 | 「正在一起...」 | 暂停, 完成, 取消 |
| `activity-paused` | 进度环脉冲闪烁，边框静止 | 「已暂停」 | 继续, 完成, 取消 |
| `activity-completed`| 卡片化为光点收入历史记录 | 「会话结束」 | 查看记录 |
| `activity-cancelled`| 卡片淡出消失 | 「已取消」 | 无 |
| `diary-empty` | 空白的半透明宣纸面板 | 「写下今天的回声...」| 生成草稿, 手动输入 |
| `diary-drafting` | 纸面上有光斑游走 | 「正在整理今天的记忆...」| 取消生成 |
| `diary-draft-ready`| 文本以打字机效果呈现 | 「这是我眼中的今天」 | 编辑内容, 保存, 废弃 |
| `diary-saving` | 保存按钮变为旋转的光环 | 「正在封存...」 | 无 (锁定界面) |
| `diary-error` | 纸面边缘泛起微弱的琥珀色 | 「保存遇到了一点问题」 | 重试 |
| `action-preview` | 深度背景模糊，居中弹窗 | 动态拉取的影响说明 | 确认执行, 取消 |
| `action-confirming`| 确认按钮呈现注水进度/加载 | 「处理中...」 | 无 |
| `action-denied` | 弹窗轻微震动，恢复正常 | 「操作已取消」 | 重新触发 |

---

## 11. Batch 2B-2 自检清单

1.  [ ] Task 卡片是否实现了 `backdrop-filter` 的磨砂玻璃效果，并在移动端支持流畅的横向滑动操作？
2.  [ ] 点击 Task 完成时，是否移除了生硬的对勾图标，替换为柔和的光晕填充动画？
3.  [ ] Task 的 Blocked 状态是否正确调用 API，并在 UI 上呈现起雾/灰绿色的非焦虑感视觉？
4.  [ ] Routine 的 Check-in 动作是否调用了 `POST /api/routines/{id}/checkins` 且伴随露珠动画？
5.  [ ] Routine 错过的天数是否只显示水痕轮廓，没有任何红色的警告或断签惩罚提示？
6.  [ ] Activity 处于 active 状态时，主界面的存在感（Presence）UI 是否同步响应了「一起做」的状态？
7.  [ ] Activity 的悬浮控制台在 pause 状态下，进度条是否呈现正确的脉冲呼吸效果？
8.  [ ] 点击「生成回顾」是否正确调用了 `POST /api/diary-entries/draft`？
9.  [ ] Diary 草稿返回后，文本框是否处于完全可编辑（`contenteditable`）状态？
10. [ ] Diary 保存时，是否展示了隐私提示（本地与专属记忆库）？
11. [ ] 触发删除 Routine 等高危操作时，是否正确弹出了 ActionPreviewConfirm 的深度模糊遮罩？
12. [ ] `/api/actions/preview` 返回的数据是否正确渲染在确认弹窗的说明区域中？
13. [ ] 确认弹窗是否采用了长按/滑动等防误触交互，而非简单的点击按钮？
14. [ ] 所有的网络请求失败（如 `diary-error`）是否都有温和的琥珀色/暖色错误提示和重试机制？
15. [ ] 确保没有任何倒计时滴答声、红色逾期警告等效率管理工具（Productivity Dashboard）的常见元素。
