# S2 核心陪伴联通验收记录

> 验收日期：2026-07-25
> 结论：通过
> 实现范围：`/api/state`、`/api/chat`、安全 adapter、请求状态、草稿恢复、fixture 回归和环境化反馈

## 设计依据

- [`luminous_frontend_design_spec_v1.md`](../../luminous_frontend_design_spec_v1.md)
- [`frontend_architecture_v1.md`](../../frontend_architecture_v1.md)
- [`s2_environmental_state_design_v1.md`](../../s2_environmental_state_design_v1.md)
- [`S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md`](../../S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md)

Gemini 请求、上下文、图片和逐次响应保存在 `/home/wz/gemini-api-traces/`，不放入项目仓库。

## 自动化证据

### Node 边界与状态测试

```bash
node --test \
  tests/frontend/s2-api-boundary.test.mjs \
  tests/frontend/s2-app-state.test.mjs \
  tests/frontend/s2-core-runtime.test.mjs
```

结果：19 tests，19 pass，0 fail。

覆盖：

- JSON、204、空正文、非法 JSON、400/404/500/503 映射；
- timeout、caller cancellation、离线与相对 `/api/` 路径限制；
- state/chat 白名单、恶意内部字段丢弃、history 清洗与上限；
- 初始加载、非乐观提交、重复提交、草稿恢复、取消、旧请求回写和 fixture 兼容。

### 浏览器验收

外部脚本：

- `/home/wz/gemini-api-traces/browser-tools/verify-s1.mjs`
- `/home/wz/gemini-api-traces/browser-tools/verify-s2.mjs`

结果：S1 fixture 回归通过；S2 mock API 验收通过；unexpected console errors 为 0。一个 503 resource console message 是错误路径测试的预期浏览器行为。

浏览器断言覆盖：

- API ready 与 warm tone 计算样式；
- 慢请求期间 non-optimistic、`readOnly`、静态等待图标；
- 503 安全文案、草稿原样恢复、珊瑚边框/焦点/反馈色与成功重试；
- 移动离线输入可编辑、发送禁用、Fixture 场景保留、4px 雾化和暗色输入材质；
- reduced-motion 无循环等待动画；
- 模拟软键盘时隐藏外围入口并保持输入可见；
- 环境层 z-index 200/201，不阻挡前景交互；
- DOM 中无技术化断网图标、后端内部字段和原始错误详情。

## 截图证据

- `desktop-ready.png`：API ready / warm tone。
- `desktop-waiting.png`：慢模型等待。
- `desktop-error.png`：retryable 503、草稿恢复和珊瑚错误反馈。
- `mobile-offline.png`：390×844 离线雾化、输入可编辑。
- `mobile-keyboard.png`：390×844 模拟软键盘模式。

## Gemini 设计与终审链

关键 trace：

1. `20260724T192123.426968Z_luminous-s2-design-round1_2dc9a225`：体验与状态设计；主端失败后备用成功。
2. `20260724T192458.134272Z_luminous-s2-impl-batch1_f69f2267`：API client/adapter 候选。
3. `20260724T193048.584562Z_luminous-s2-static-network-states_ae20d1d5`：输出截断，未采纳。
4. `20260724T193540.349322Z_luminous-s2-static-network-states-completion-ret_f863ea94`：备用端完整修复。
5. `20260724T193853.666314Z_luminous-s2-impl-app-state_31e4a8e6`：AppState 候选。
6. `20260724T194733.241232Z_luminous-s2-impl-core-runtime_e51d8d33`：核心运行时候选。
7. `20260724T195618.256148Z_luminous-s2-multimodal-final-audit_39777ef0`：初次截图审计，条件通过。
8. `20260724T200121.440717Z_luminous-s2-environmental-state-design_5c59f3f5`：环境态设计初稿。
9. `20260724T200359.669775Z_luminous-s2-environmental-design-repair_e8a57a9b`：修复输入行为与视觉层拓扑矛盾。
10. `20260724T200639.951372Z_luminous-s2-environment-batch1-implementation_79f0597f`：环境修正 Batch 1。
11. `20260724T200849.386239Z_luminous-s2-environment-batch2-implementation_8d4fc240`：环境修正 Batch 2。
12. `20260725T014208.468868Z_luminous-s2-post-remediation-audit-retry_977d5d32`：终审；主端失败后备用 attempt 2 成功，指出 8px 离线雾化过强。
13. `20260725T015028.775572Z_luminous-s2-audit-selector-repair-primary-retry_3678a211/attempt-004.stdout.txt`：真实选择器修复补丁；logger 因误用 exact-equality 哨兵标记失败，但输出完整且以 `PATCH_COMPLETE` 结束。

## 失败处理记录

- 传输失败：按同一输入重试，并在主/备端点间切换。
- 截断或语义不完整：不采纳候选；补充精确约束后重新调用。
- Gemini 设计与工程红线冲突：保留视觉意图，明确指出矛盾，再让 Gemini 输出修订版。
- 示例选择器与真实 DOM 不符：不直接粘贴；把真实文件重新提供给 Gemini 修复。
- 浏览器截图暴露过度雾化：以最终过渡截图而非过渡初始帧为准，降低至 Gemini 指定的 4px 后重验。
- 自动验收器自身错误：区分应用缺陷、预期 503 控制台消息和验证脚本误判，并分别记录。

## 已知边界

- 后端没有用户安全的历史读取接口，刷新后不恢复服务端对话历史。
- S2 不渲染 `role_thinking`、`role_action`、memory、ledger、prompt、analysis 或 meta；这是安全白名单决策。
- API 默认模式需要同源后端；静态演示使用 `?mode=fixture`。
