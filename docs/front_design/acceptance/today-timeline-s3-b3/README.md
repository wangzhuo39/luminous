# S3 B3 Today / Timeline 验收记录

> 验收日期：2026-07-26
> 结论：通过

## 1. 范围

B3 将 S1 的静态 Today 摘要升级为一个可访问的单 dialog 垂直切片：首次打开懒加载 Today、手动刷新、最多四类自然展开、Completed 折叠、显式进入 Timeline，以及 loading/empty/error/retry/offline 安全状态。本批不包含 Task/Routine 等资源写操作。

## 2. 自动化结果

Node 全量回归：

```bash
rtk node --test tests/frontend/*.test.mjs
```

```text
tests 120
pass 120
fail 0
```

B3 浏览器验收：

```bash
rtk python -m http.server 4173 \
  --directory /home/wz/luminous/apps/companion-web/companion-ui
```

另一个终端执行：

```bash
rtk node tests/frontend/s3-browser-acceptance.mjs
```

```text
B3_BROWSER_ACCEPTANCE_OK viewports=2 scenarios=2 screenshots=6
```

浏览器断言包括：fixture 零 `/api/*` 请求、Today 首次打开、Timeline 显式进入与顺序、桌面/移动无横向溢出、移动 reduced-motion、焦点进入 dialog、关闭后焦点返回入口、空态、安全 503 错误态、无内部错误正文泄漏。503 场景只允许浏览器自身的预期资源失败消息，未出现意外 console/page error。

机器可读结果见 `browser-acceptance.json`。

## 3. 截图证据

- `desktop-1440x1000-today.png`
- `desktop-1440x1000-timeline.png`
- `mobile-390x844-today.png`
- `mobile-390x844-timeline.png`
- `desktop-empty.png`
- `desktop-error.png`

## 4. Gemini 多模态终审

完整请求、4 张输入截图副本、响应、端点尝试和哈希保存在：

```text
/home/wz/gemini-api-traces/runs/20260726T014330.983607Z_luminous-s3-b3-visual-audit_3b209ff0/
```

主端点首次 HTTP 200 但输出未满足结束标记，备用端点第 2 次返回完整审查。Gemini 判定 Today 桌面/移动结构成立，但 Timeline 的高不透明吸顶背景形成“嵌套黑盒”。按该视觉结论修复后，进一步消除了透明层叠导致的近黑合成：Timeline 标题改为同层透明普通标题，仅保留轻分隔线；最终 6 张截图均重新生成。

## 5. 验收中修复的问题

1. dialog 打开后焦点未可靠进入弹层：`overlays.js` 现在优先聚焦关闭按钮，回退到首个可操作控件；关闭后仍返回原入口。
2. Timeline 标题栏与外层透明背景叠加成近黑矩形：取消吸顶叠色，恢复同一空间材质。
3. error 浏览器测试最初把预期 503 资源日志当成意外错误：验收脚本现在只白名单精确 503 日志，其他 console/page error 仍失败。

## 6. 已知边界

- B3 只读；Task/Routine 从 B4 开始。
- API 空态与 503 使用浏览器 route mock，真实后端联调留在 S3 B9。
- Playwright 仅用于验收，不是产品运行时依赖，也未引入构建系统。
