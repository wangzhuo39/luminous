# S5 产品化范围与架构契约 v1

> 状态：已实现并验收（2026-07-26）
> 适用目录：`apps/companion-web/companion-ui/`

## 1. 结论

S5 保持原生 HTML/CSS/ES Modules、单文档空间模型和现有小型状态容器，不引入框架、构建链、第三方 router、IndexedDB 或全局状态库。当前复杂度仍可由 feature controller、纯状态模块与严格 adapter 清晰隔离；迁移工具链不会增加用户价值。

新增产品化边界：

```text
manifest.webmanifest + assets/
          │
service-worker.js ── 静态 app shell cache
          │          /api/* 永远 network-only
          ▼
features/productization/
  pwa-controller.js       安装资格、waiting update、连接呈现
  draft-recovery.js       sessionStorage 未发送草稿
  space-router.js         ?space= 空间级 History 同步
```

## 2. 能力矩阵

| 能力 | S5 结论 | 边界 |
| --- | --- | --- |
| Manifest / 安装身份 | 实现 | `beforeinstallprompt` 就绪后才显示入口，用户手势触发 |
| 离线静态外壳 | 实现 | 只缓存同源静态资源；离线隐藏对话流、禁用发送 |
| Service Worker 更新 | 实现 | waiting 后低刺激提示，用户点击 `SKIP_WAITING`，随后 reload |
| 未发送草稿恢复 | 实现 | `sessionStorage`、v1、8000 字、24h TTL、成功发送即清除 |
| 空间级深链 | 实现 | 仅 today/outbox/memory/privacy，保留 `mode`，非法值移除 |
| 系统通知 / Push / VAPID | 延期 | 无后端订阅、权限和投递契约，不请求权限 |
| Background Sync / 离线写队列 | 不做 | 断网明确拒绝写入，不伪装“稍后发送” |
| 聊天历史恢复 | 延期 | 无 user-safe history DTO；静态壳不保存或展示历史 |
| 资源级 URL | 不做 | opaque key、Memory/Outbox 资源 ID 不进入 URL |
| 跨设备同步 | 延期 | 无身份、账号和同步契约 |

## 3. 缓存与更新不变量

1. `service-worker.js` 使用显式、版本化 shell 列表；安装任一资源失败时不提交不完整缓存。
2. `/api/`、非 GET、跨域请求不进入 CacheStorage。
3. navigation 使用 network-first，失败回退缓存 `index.html`；静态资源 cache-first。
4. 新 worker 不自动 `skipWaiting`；只有用户点击“窗外有新的晨光”才切换。
5. 发送中、输入中或资源写操作 pending 时更新按钮禁用，避免丢失输入和编辑状态。
6. `controllerchange` 只 reload 一次。

## 4. 存储边界

唯一新增 storage key：

```text
luminous.unsent-chat-draft.v1
```

值只包含 `{ version, text, savedAt }`。禁止保存：API raw response、已发送消息、助手回复、资源、opaque key、trace、prompt、token、用户偏好或密钥。解析失败、版本不符、超长、未来时间或超过 24 小时即删除。

## 5. URL 边界

- 合法：`/?mode=fixture&space=privacy`；
- 关闭空间时只删除 `space`，保留 `mode` 和其他非资源查询参数；
- `pushState` 记录打开/关闭，`popstate` 恢复空间；
- `?space=unknown` 静默规范化；
- 不需要 History API fallback，因为仍由 `/` 单文档入口承载。

## 6. 部署边界

Python 静态服务器显式返回 `.webmanifest` 的 `application/manifest+json`，静态资源 `Cache-Control: no-cache`，并增加 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer` 和最小 Permissions Policy。Service Worker 依赖安全上下文；本地 `localhost` 可用于验收，生产必须使用 HTTPS。

## 7. 重新评估条件

只有出现以下事实才重新评估框架、构建链或正式 router：独立页面需要服务端 fallback；原生模块形成实测循环依赖；状态同步缺陷持续跨 feature 出现；CI 需要打包、代码分割或长期多人维护。单纯视觉升级不触发工程迁移。
