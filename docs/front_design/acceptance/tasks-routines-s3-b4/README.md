# S3 B4 Task / Routine 验收

## 完成范围

- Task：懒加载列表、详情、创建/编辑、状态变更、归档确认、Step 添加与切换；
- Routine：懒加载列表、详情、创建/编辑、当次会话 check-in、停用确认和 inactive 只读；
- Today 资源入口、写成功回刷、列表/Today 焦点归还和滚动恢复；
- pending 单飞、AbortController、离线中止、失败精确草稿恢复、错误白名单；
- opaque key 不进入 DOM。

## 自动化结果

- 全量 Node：136/136；
- B4 浏览器：`B4_BROWSER_ACCEPTANCE_OK scenarios=3 screenshots=6`；
- 晶格温室视觉专项：`CRYSTAL_SOLARIUM_BROWSER_OK scenarios=3 screenshots=4`；
- Chromium console/pageerror：为空；
- JS syntax 与 `git diff --check`：通过。

## 截图

- `desktop-task-empty.png`
- `desktop-task-detail.png`
- `desktop-routine-checked.png`
- `desktop-routine-inactive.png`
- `desktop-task-api-error.png`
- `mobile-task-form-keyboard.png`

这些截图已在晶格温室视觉重构后重新生成。机器可读的请求数量、触控热区、移动布局和错误恢复结果位于 `browser-acceptance.json`。
