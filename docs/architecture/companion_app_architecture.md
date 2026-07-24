# AI 伴侣 App 架构

> 日期：2026-07-23  
> 关联：[companion_foundation_implementation_roadmap.md](./companion_foundation_implementation_roadmap.md)、[scheduler.md](./scheduler.md)、[roleplay_companion_architecture.md](./roleplay_companion_architecture.md)

这份文档定义我们真正要做的产品壳：一个带 Live2D 虚拟形象的 AI 伴侣 App。  
它不是“聊天网页升级版”，而是承载长期陪伴体验的主入口。

当前 `apps/companion-web/` 里的静态 demo 只适合作为预览页、调试页或过渡期壳层；后续产品主线应迁移到独立 App。

---

## 1. 为什么必须做自己的 App

如果后面要加入 Live2D、语音、主动通知、状态反馈和长期陪伴节奏，前端就不能只是一个聊天框。

真正需要的是一个“伴侣壳”：

- 角色形象一直在
- 状态会呼吸、会看你、会说话
- 聊天只是其中一种交互
- 通知、提醒、主动联系都能自然出现
- 语音和表情是体验核心，不是附属功能

所以终局不是“网页 UI”，而是“独立 App”。

---

## 2. 产品定位

### 2.1 一句话

一个长期存在的 AI 伴侣 App：有自己的形象、状态、记忆、主动联系、语音和提醒能力。

### 2.2 核心体验

- 你打开它时，她就在
- 你不说话时，她也有自己的状态
- 她会记得你
- 她会在合适的时候主动找你
- 她的表情、动作和语气会随着关系变化
- 她不是工具壳，而是陪伴对象

---

## 3. 总体分层

建议把 App 分成 5 层。

### 3.1 Companion Runtime

这是我们已经在做的底座：

- memory
- state
- proactive
- scheduler
- trace / ledger
- prompt builder

它不关心 UI 长什么样，只负责“她是谁、她记得什么、此刻在想什么、是否该主动联系”。

### 3.2 App Shell

这是桌面应用本体：

- 窗口管理
- 导航
- 页面切换
- 设置
- 登录 / 配置
- 本地存储
- 通知入口

### 3.3 Avatar Layer

Live2D / 动画 / 表情层：

- 待机呼吸
- 说话口型
- 视线跟随
- 情绪表情
- 高兴、困、担心、安慰、沉默等状态
- 与语音同步

### 3.4 Interaction Layer

用户实际操作层：

- 聊天
- 语音
- 主动通知
- 任务 / 提醒
- 记忆浏览
- 关系查看

### 3.5 Dev / Debug Layer

给我们自己看的：

- state 面板
- memory 面板
- ledger 面板
- proactive 面板
- outbox 面板
- job 面板

这层将来可以隐藏，不进入正式用户主路径。

---

## 4. 推荐技术路线

### 4.1 桌面端优先

推荐先做桌面 App，再考虑移动端。

原因：

- Live2D 在桌面 Chromium 环境最稳
- 语音、通知、窗口常驻、后台任务都更好做
- 伴侣感的沉浸式展示在桌面更容易成立

### 4.2 推荐栈

第一选择：

- Electron
- React
- TypeScript
- Vite
- Live2D Cubism Web SDK

可选配套：

- Zustand / Redux Toolkit：状态管理
- Tailwind / CSS Modules：样式
- React Router：页面路由
- Web Audio API：语音与音效
- localStorage / IndexedDB / 本地 SQLite：偏好和 UI 状态

### 4.3 为什么先选 Electron

- Live2D 生态成熟
- Chromium 对动画和音频支持稳定
- 易于接入系统通知、托盘、快捷键、文件访问
- 比较适合长期陪伴型桌面壳

Tauri 以后可以再评估，但不建议作为第一版主路径。

---

## 5. App 的页面结构

建议不是传统三栏聊天，而是“中心角色 + 周边功能”的布局。

### 5.1 主舞台

中央区域是角色本体：

- Live2D / 头像 / 半身像
- 表情层
- 动作层
- 语音波形
- 当前状态文案

### 5.2 聊天区

聊天是主舞台下方或侧边的一块：

- 用户消息
- 伴侣消息
- 角色动作标签
- 可折叠思考 / 安抚提示

### 5.3 状态区

显示当前运行时摘要：

- mood
- energy
- support_need
- relationship
- recent_topics
- proactive readiness

### 5.4 记忆区

用于查看“她为什么记得这个”：

- 长期记忆
- 最近事件
- 证据原文
- 关系线索
- open loops

### 5.5 通知区

用于接收主动联系和提醒：

- 主动问候
- 纪念日
- 提醒
- 任务完成
- 低频关心

### 5.6 设置区

包括：

- 模型配置
- 角色设定
- 语音配置
- 通知开关
- 免打扰
- Live2D 皮肤 / 角色资源
- 数据导出 / 删除

---

## 6. Avatar 设计原则

Live2D 不应该只是一个“挂件”，而应该是状态表达器。

### 6.1 角色动作来源

动作由 runtime state 驱动，而不是随机播放。

例如：

| 状态 | Avatar 表现 |
| --- | --- |
| steady | 轻微呼吸、自然注视 |
| listening | 视线跟随、轻微前倾 |
| thinking | 轻微停顿、目光偏移 |
| warm | 微笑、放松 |
| concerned | 眼神更认真、动作变慢 |
| tired | 低频呼吸、动作更少 |
| protective | 表情收敛、语气稳 |
| speaking | 口型与音频同步 |

### 6.2 Avatar 与 state 的关系

Avatar 只消费状态，不自己决定状态。

```text
CompanionRuntime
  -> state / proactive / prompt / presence
  -> App Shell
  -> Avatar Layer
```

### 6.3 Avatar 与语音的关系

如果后续加入语音：

- STT 结束时，avatar 进入 listening
- TTS 播放时，avatar 进入 speaking
- 结束后回到 steady / warm / concerned

---

## 7. App 与 Runtime 的数据流

### 7.1 聊天链路

```text
user input
  -> app shell
  -> runtime /api/chat
  -> reply + state + memory + proactive + prompt trace
  -> app shell render
  -> avatar update
```

### 7.2 主动通知链路

```text
scheduler tick
  -> proactive decision
  -> outbox
  -> notification bridge
  -> app shell / desktop notification
  -> user reply
  -> runtime state update
```

### 7.3 记忆查看链路

```text
memory panel
  -> /api/memory
  -> evidence / source event
  -> UI 展示“她为什么记得这个”
```

---

## 8. 通知体系

App 自己做通知层，不要把通知理解成单纯的“弹窗”。

### 8.1 通知类型

- 站内通知
- 桌面系统通知
- 任务卡片
- 提醒条
- 主动联系草稿
- 语音呼出（以后）

### 8.2 通知原则

- 低频
- 可关闭
- 可延迟
- 可回看
- 有上下文

### 8.3 与 outbox 的关系

`outbox` 是 runtime 的待投递队列。  
App 通知层只是它的一个消费者。

```text
outbox -> notification adapter -> desktop / in-app / future mobile
```

---

## 9. 账号与本地数据

第一版建议本地优先：

- 本地配置
- 本地缓存
- 本地窗口状态
- 本地 avatar 资源
- 本地历史记录

后续再考虑云同步。

App 不应该把“陪伴感”建立在必须联网和必须登录的前提上。

---

## 10. 推荐工程结构

未来可以长成这样：

```text
apps/
  companion-app/         # 正式桌面 App
  companion-preview/     # 当前 demo / 调试页

luminous/runtime/   # runtime
```

### companion-app 内部建议

```text
companion-app/
  src/
    app/
    pages/
    components/
    avatar/
    notifications/
    bridge/
    store/
    styles/
```

### runtime 与 app 的边界

- runtime：状态、记忆、调度、主动联系
- app：渲染、交互、通知、avatar、配置

---

## 11. 迁移策略

现在的 `companion-web` 不要强行改成最终产品形态。

建议是：

1. 保留它当 preview / debug 页面
2. 新建正式 `companion-app`
3. 逐步把核心交互迁过去
4. 最终 preview 只做调试和设计验证

这样不会被 demo 的静态结构限制住。

---

## 12. 分阶段落地

### Phase A：App Shell

- Electron 壳
- 基础页面
- runtime 接入
- settings

### Phase B：Avatar

- Live2D 接入
- 表情映射
- 状态驱动动作

### Phase C：Notification

- 站内通知
- 桌面通知
- outbox 消费

### Phase D：Voice

- 麦克风
- TTS
- 说话状态

### Phase E：多端扩展

- 手机端
- 平板端
- 未来 VRM / 3D 形象

---

## 13. 当前结论

我们不应该把自己限制在“网页 demo”里。  
更合理的路线是：

- 运行时继续做强
- App 作为真正的陪伴入口
- Live2D 作为核心体验层
- Demo 只保留为 preview / debug

这会让后面的陪伴感、通知、语音和角色存在感都自然很多。

