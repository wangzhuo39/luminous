# S3 B9 最终集成验收

> 日期：2026-07-26
> 范围：S3 B1–B9 + Crystal Solarium v2

## 新增 B9 场景

- API/生产模式不存在 `__luminousActionFixture`，不会自行触发 `/api/actions/*`。
- B8 接入后 S2 chat 和 Today 懒加载仍工作。
- 320×568 reduced-motion 下长 Action 光签完整可见、按钮可用、无横向溢出。
- Action 收起后物理门户恢复交互并可打开 Today。

```text
production-gate-chat-today              passed  1 screenshot
mobile-320-action-portal-recovery       passed  2 screenshots
```

## 全量浏览器矩阵

以下 7 套脚本在同一最终工作树串行通过：

```text
tests/frontend/s3-browser-acceptance.mjs                    PASS
tests/frontend/s3-b4-browser-acceptance.mjs                 PASS
tests/frontend/s3-b5-browser-acceptance.mjs                 PASS
tests/frontend/s3-b6-browser-acceptance.mjs                 PASS
tests/frontend/s3-b7-browser-acceptance.mjs                 PASS
tests/frontend/s3-b8-browser-acceptance.mjs                 PASS
tests/frontend/crystal-solarium-browser-acceptance.mjs      PASS
```

新增集成脚本：

```text
tests/frontend/s3-b9-integration-acceptance.mjs             PASS
```

## Node 回归

```bash
rtk node --test tests/frontend/*.test.mjs
```

```text
tests 162
pass 162
fail 0
```

## 截图

- `desktop-production-chat-today-no-action-trigger.png`
- `mobile-320-action-light-tag.png`
- `mobile-320-portal-recovers-after-action.png`

## 安全与架构结论

- 单主场景、唯一 Today dialog、无新增 route/嵌套 modal。
- API 与 fixture 双数据源边界保持；生产 Action 触发门控。
- raw response、内部字段、opaque key 不进入可见 DOM/属性/console/storage。
- 写入不乐观；pending/error/retry、Abort、过时响应和重复提交门继续有效。
- 320/390/桌面、键盘、reduced-motion 和焦点恢复有自动化证据。

## 最终多模态审计

```text
/home/wz/gemini-api-traces/runs/20260726T083035.176629Z_luminous-s3-b9-final-multimodal-audit_c4949ef6/
```

Gemini 9 图终审：总分 96，视觉一致性 98，陪伴感 95，桌面 96，移动 95；S3 可正式关闭，无 P0。关于 44px 光签触控区的建议已经由 B8 自动化断言覆盖；长列表边缘渐隐作为非阻塞观察项留给 S4 内容增长时复核。
