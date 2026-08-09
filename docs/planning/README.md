# 规划状态

更新时间：2026-08-05

当前已批准下一轮产品主线：在已有长期记忆、主动联系、Android 通知和陪伴生活流上，依次建设语音存在、共同刷内容和受控上下文 adapter。

目标架构以 [Luminous Companion Runtime 目标架构](../architecture/luminous_companion_runtime_architecture.md) 为唯一规范性入口；阶段计划描述交付顺序，不得反向改变其中的模块所有权和依赖边界。

## 当前产品计划

- [语音存在与共同刷内容拓展计划](2026-08-05-voice-and-shared-entertainment-expansion-plan.md)：先完成按住说话、角色语音与主动语音来信，再支持把小红书帖子、视频和网页分享给栖光，形成可续接、可回看、可删除的共同娱乐活动。

## 学术研究计划

- [About You, About Me, About Us：DAI 2026 论文研究与实施计划](2026-07-28-relationship-aware-companion-dai-2026-paper-plan.md)：研究长期陪伴 Agent 如何在理解用户、保持角色和延续共同相处历史之间实现有证据、有边界的适应。
- [IntentGraph：DAI 2026 论文研究与实施计划](2026-07-27-intentgraph-dai-2026-paper-plan.md)：将自然语言未来意图编译为可执行时序图；研究代码与产品主线分离，当前处于基准复现和方法验证阶段。

## 已完成记录

- [陪伴生活流实施记录](2026-07-23-companion-life-flow-implementation.md)：任务、例行、活动会话、日记与统一时间线已交付。
- [前端 S1–S5 追踪表](../front_design/S2_S5_IMPLEMENTATION_TRACKER.md)：晶格温室、核心陪伴、生活流、静默空间与 PWA 产品化已交付。
- [S5 实施与验收记录](../front_design/s5_03_implementation_plan_v1.md)：175 项 Node 测试、九套 Chromium 回归与 Gemini 多模态复审已完成。

## 后续候选（未排期）

- [共读活动与内容记忆锚点](2026-07-23-shared-reading-activity-iteration.md)：保留为历史设计参考；其内容 anchor、批注和进度语义已被吸收到“共同刷内容”，读书不再是近期主场景。
- 浏览器系统通知、Push/VAPID 与通知资源深链：需先形成权限、订阅、投递和隐私契约；当前 PWA 静态壳与空间深链已经完成。
- 人格可移植、数据导入与迁移：在有真实用户和迁移需求前不启动。

已完成或不再适用的阶段性计划已删除，避免它们被误读为当前工作项。
