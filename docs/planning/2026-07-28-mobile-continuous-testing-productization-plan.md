# Luminous 手机持续测试工程化方案

状态：待批准草案

基线：`agent/frontend-baseline` / `e1299bd3e62d30bc58f2cf670d447364b95555c8`

目标：将当前工程原型改造成可由一名真实测试者通过手机连续使用的单机内测产品。

## 1. 结论

本轮不做多租户 SaaS，不更换前端技术栈，也不重写现有 runtime。采用“一台本机、一套独立数据、一名测试者”的部署边界，在现有真实 HTTP、SQLite、worker、PWA 和 public DTO 基础上补齐：

1. 稳定 HTTPS 手机入口；
2. 正常登录与会话，不把长期 Bearer Token 放进页面；
3. API 与 worker 开机自启、失败重启和健康检查；
4. 数据目录、备份、恢复和版本回滚；
5. 真实模型、主动联系、通知、反馈和重启持久化验收；
6. 只记录运行元数据的可观测性，不记录对话正文和模型内部信息。

推荐的私测访问方式是服务器侧 Cloudflare Tunnel（或同类 HTTPS Tunnel）：后端仍只监听 `127.0.0.1:8000`，服务器向外建立隧道并提供稳定的 `https://test.example.com` 地址。测试者只需打开链接、输入一次邀请码/测试密码，之后由 HTTPS Cookie 保持登录；不安装 VPN、不注册第三方网络账号、不配置手机网络。不要直接把 `0.0.0.0:8000` 暴露到公网。若没有域名，可先使用带 HTTPS 的临时 Tunnel 做短期验收，但持续测试必须换成固定域名。

## 2. 当前基线与缺口

当前已经具备：

- 同源静态页面和 `/api/*`；
- SQLite WAL、状态/记忆/事件/outbox 持久化；
- public DTO、Origin 检查、Bearer 边界和写请求幂等；
- API 重启恢复与真实模式浏览器验收；
- 常驻 worker 循环、主动联系、DND、冷却、receipt 和 feedback；
- PWA manifest、离线壳、更新提示、移动端 safe-area 和键盘处理；
- webhook、Telegram、Bark 通知桥。

持续手机测试仍缺少：

- 生产进程管理、TLS 入口、稳定域名和安装流程；
- 独立于 Git checkout 的数据目录；
- 登录页、HttpOnly 会话、注销和会话过期；
- worker 心跳、深度健康检查和运行告警；
- Web Push 订阅、推送和通知深链；
- 自动备份、恢复演练、版本标识和回滚；
- 真实模型与真实手机的重启、断网、通知和长期运行证明。

当前 `CompanionRuntimeStore.for_project()` 把数据放在 `<project_root>/outputs/companion_runtime`。这适合开发，不适合发布版本切换。当前 SQLite 连接已经启用 WAL 和 foreign keys，但没有显式 `busy_timeout`。当前 public 模式只支持 Bearer Token，网页通过 `window.__LUMINOUS_API_TOKEN__` 获取，缺少可交付的登录流程。当前 Service Worker 只处理 install、activate、message 和 fetch，没有 push 或 notificationclick。

## 3. 目标拓扑

```text
测试者手机（普通浏览器/PWA）
  -> 固定 HTTPS 域名（Cloudflare Tunnel）
  -> 127.0.0.1:8000 luminous-api
       -> OpenAI-compatible real model
       -> /var/lib/luminous/runtime/runtime.sqlite3

systemd
  -> luminous-api.service
  -> luminous-worker.service
  -> luminous-backup.timer

luminous-worker
  -> proactive / reminder / outbox jobs
  -> Web Push
  -> Bark or Telegram fallback
```

约束：

- API 不直接监听公网网卡，Tunnel 只连接 `127.0.0.1`；
- 单部署只服务一个测试者；
- 前后端同源，不开放通配 CORS；
- 模型密钥、会话密钥和 VAPID 私钥只存在 `/etc/luminous/luminous.env`；
- 运行数据只存在 `/var/lib/luminous`，Git checkout 可随时替换；
- 日志不得包含消息正文、prompt、memory evidence、token 或 provider response body。

## 4. 具体修改

### P0-A：配置和数据目录

修改：

- `luminous/runtime/config.py`
  - 增加 `data_dir`、`release_revision`、`session_secret`、`tester_password_hash`；
  - 增加 `LUMINOUS_DATA_DIR`、`LUMINOUS_RELEASE_REVISION`、`LUMINOUS_SESSION_SECRET`、`LUMINOUS_TESTER_PASSWORD_HASH`；
  - public 模式启动时校验 HTTPS 外部 Origin、会话密钥和密码哈希；
  - 保留 Bearer Token，仅供自动化和紧急运维，不作为手机端主认证。
- `luminous/runtime/application/runtime.py`
  - 所有 runtime/life-flow store 从 `config.data_dir` 创建；
  - 不再通过 Git checkout 位置推导生产数据路径。
- `luminous/runtime/worker.py`
  - 使用同一个 `config.data_dir`；
  - 启动时验证 API 与 worker 指向同一数据库。
- `luminous/runtime/infrastructure/runtime_store.py`
  - 增加 `PRAGMA busy_timeout=5000`；
  - 增加 `runtime_health`、`auth_sessions`、`push_subscriptions` 和 `schema_migrations` 表；
  - 保持 WAL，备份使用 SQLite backup API，不直接复制活跃数据库文件。
- `luminous/runtime/infrastructure/life_flow_store.py`
  - 对齐 WAL、foreign keys 和 busy timeout；
  - 明确两个 store 是否共用同一 SQLite 文件，禁止配置成不同数据根。
- 新增 `.env.example`
  - 只列变量名和说明，不放真实值；
  - 区分 required、optional 和 development-only。

验收：

- 切换 Git commit 后历史、记忆、设置和 outbox 不变；
- API 与 worker 并发运行 30 分钟无 `database is locked`；
- 缺少生产密钥时启动失败，而不是降级为无认证 local 模式。

### P0-B：登录、会话和同源边界

新增：

- `luminous/runtime/infrastructure/auth.py`
  - 使用随机 256-bit session id；
  - 数据库只保存 session id 的 SHA-256 摘要、创建时间、过期时间和撤销时间；
  - 密码使用 scrypt 或 Argon2 哈希，不保存明文；
  - 登录失败按 IP 和时间窗口限速。
- HTTP API：
  - `POST /api/auth/login`；
  - `POST /api/auth/logout`；
  - `GET /api/auth/session`。
- Cookie：
  - `__Host-luminous_session`；
  - `Secure; HttpOnly; SameSite=Lax; Path=/`；
  - 7 天绝对过期，24 小时空闲过期；
  - 登录和注销后轮换/撤销 session。
- `apps/companion-web/companion-ui/js/features/auth/`
  - 登录门、会话恢复、过期提示和注销；
  - 不把密码、session 或 Bearer Token写入 AppState、DOM 日志和 storage。
- `apps/companion-web/companion-ui/js/services/api-client.js`
  - 默认使用同源 Cookie；
  - `401` 转为显式 `auth_required`；
  - 保留自动化依赖注入，不再依赖 `window.__LUMINOUS_API_TOKEN__` 作为产品路径。
- `luminous/runtime/infrastructure/http.py`
  - public API 接受有效 session 或自动化 Bearer；
  - 所有写请求继续校验精确 Origin；
  - 登录接口也执行 Origin、body size 和 rate-limit 检查；
  - `GET /api/health` 只返回浅层状态，不暴露路径、模型、任务和数据库信息。

不做：本阶段不增加注册、找回密码、社交登录、管理员后台或多用户表迁移。

验收：

- 未登录只能看到登录门和浅层健康状态；
- 登录、刷新、PWA 重启、注销和过期流程在 iOS/Android 均成立；
- Cookie 无法从 JavaScript 读取；
- 非允许 Origin 的登录与写请求返回 `403`；
- 连续错误密码触发 `429`，不会在日志中打印密码。

### P0-C：systemd、HTTPS 和发布脚本

新增：

- `deploy/systemd/luminous-api.service`
- `deploy/systemd/luminous-worker.service`
- `deploy/systemd/luminous-backup.service`
- `deploy/systemd/luminous-backup.timer`
- `deploy/cloudflared/config.yml`
- `deploy/cloudflared/README.md`
- `scripts/deploy/install-local-test.sh`
- `scripts/deploy/smoke-test.sh`
- `scripts/deploy/rollback.sh`

systemd 要求：

- 独立系统用户 `luminous`；
- `WorkingDirectory=/opt/luminous/current`；
- `EnvironmentFile=/etc/luminous/luminous.env`；
- API 固定监听 `127.0.0.1:8000`；
- `Restart=on-failure`、合理的 start limit 和 30 秒停止超时；
- `UMask=0077`、`NoNewPrivileges=true`、`PrivateTmp=true`、`ProtectSystem=strict`；
- 仅允许写 `/var/lib/luminous`；
- API 和 worker 分开重启，worker 故障不拖垮聊天；
- journald 日志限额和保留策略明确。

发布目录：

```text
/opt/luminous/releases/<git-sha>/
/opt/luminous/current -> /opt/luminous/releases/<git-sha>/
/etc/luminous/luminous.env
/var/lib/luminous/runtime/
/var/lib/luminous/backups/
```

发布流程：

1. checkout 指定 commit 到新 release 目录；
2. 创建 venv 并安装锁定依赖；
3. 在临时数据副本上执行 schema migration；
4. 运行 backend、frontend 和 real-mode smoke test；
5. 原子切换 `current` symlink；
6. 依次重启 API、worker；
7. 检查版本、健康和一次真实聊天；
8. 失败时切回上一 release，不回滚用户数据；数据库变更必须向前兼容。

Cloudflare Tunnel：

- Tunnel 凭据只存在服务器 `/etc/luminous/cloudflared/credentials.json`；
- ingress 只转发到 `http://127.0.0.1:8000`，不开放本机 API 端口；
- DNS 使用固定测试域名，`LUMINOUS_CORS_ORIGINS` 只包含最终 HTTPS Origin；
- 可选启用 Cloudflare Access 作为外层紧急闸门，但正常测试体验由 Luminous 自己的登录门负责；
- 测试结束后撤销 Tunnel、会话和测试邀请码。

### P0-D：健康、日志、备份和恢复

修改：

- worker 每次 tick 更新 `runtime_health(component='worker')`，保存最后成功、最后失败和连续失败数；
- API 深度健康检查验证数据库读写、worker 心跳新鲜度和模型配置；
- 深度健康信息只供本机 smoke script 使用；
- HTTP 日志改为结构化 JSON：timestamp、request_id、method、route template、status、latency_ms；
- 模型调用日志只记录 provider、model、latency、token 数和错误类别；
- 所有日志统一调用 redaction helper。

备份：

- 每 6 小时执行 SQLite online backup；
- 每日保留 7 份，每周保留 4 份；
- 备份后执行 `PRAGMA integrity_check`；
- 备份目录权限 `0700`；
- 至少完成一次“空目录 -> 恢复 -> 启动 -> 历史可见”的演练。

验收：

- 杀掉 API/worker 后 systemd 自动恢复；
- 重启本机后 2 分钟内页面、聊天和 worker 全部 ready；
- worker 停止超过两个 tick 后深度健康失败并告警；
- 从备份恢复后聊天、记忆、设置、任务和 outbox 均存在；
- 日志扫描不包含测试对话、prompt、API key 和 Cookie。

### P1-A：手机主动通知

首轮保底：

- iPhone 测试者优先配置现有 Bark；
- Android 或跨平台测试者可先用 Telegram；
- 通知内容只放简短文案和 opaque message id，不放记忆证据或内部 trace；
- 点击通知打开 HTTPS 深链并进入 Outbox。

正式 Web Push：

- 使用成熟 Web Push 库，不自行实现加密协议；
- 新增 VAPID 公私钥配置，私钥仅在服务器；
- 新增：
  - `GET /api/push/vapid-public-key`；
  - `POST /api/push/subscriptions`；
  - `DELETE /api/push/subscriptions/{id}`；
- subscription 保存 endpoint、p256dh、auth、设备标签、创建/最后成功时间和状态；
- endpoint 返回 `404/410` 时自动停用；`429/5xx` 进入有上限的退避重试；
- `NotificationBridge` 增加 `web_push` provider，并继续写 receipt；
- `service-worker.js` 增加 `push` 和 `notificationclick`；
- 新增 `js/features/productization/push-controller.js`；
- 权限只能由用户在通知设置中主动触发；拒绝后不循环弹窗；
- iOS 明确提示先“添加到主屏幕”，但不在正常界面展示技术说明。

验收：

- Android Chrome PWA 和 iOS 16.4+ 主屏 PWA 各收到一条真实通知；
- 页面关闭后仍能收到；
- 点击进入正确 Outbox message；
- DND、quiet hours、daily limit 和 cooldown 生效；
- 撤销权限或删除订阅后不再发送；
- 重复 worker tick 不产生重复通知。

### P1-B：版本、更新和反馈闭环

新增：

- `GET /api/version` 返回 release revision 和 public schema version；
- HTML/manifest/service worker 使用同一 release revision；
- 前端检测 API revision 与 shell revision 不一致时提示更新；
- 更新失败保留旧 shell，不产生白屏；
- Outbox feedback 增加“太频繁、时机不对、内容不贴切、喜欢这次”四类产品反馈；
- 增加隐私安全的“报告问题”入口，只上传版本、route、error code、网络状态和用户主动填写内容。

## 5. 测试修改

后端新增：

- `tests/backend/test_auth_session.py`
- `tests/backend/test_deployment_config.py`
- `tests/backend/test_runtime_health.py`
- `tests/backend/test_backup_restore.py`
- `tests/backend/test_push_delivery.py`
- `tests/backend/test_process_restart_e2e.py`

前端新增：

- `tests/frontend/auth-gate.test.mjs`
- `tests/frontend/push-controller.test.mjs`
- 扩展 `tests/frontend/s5-pwa-assets.test.mjs`，从“禁止 Push API”改为验证受控 Push；
- `tests/frontend/mobile-continuous-test-browser-acceptance.mjs`。

真实设备验收矩阵：

| 场景 | iPhone Safari/PWA | Android Chrome/PWA |
| --- | --- | --- |
| 首次登录与刷新恢复 | 必测 | 必测 |
| 键盘、safe-area、横竖屏 | 必测 | 必测 |
| 安装、离线壳、更新 | 必测 | 必测 |
| 真实模型慢响应与重试 | 必测 | 必测 |
| 页面关闭后的主动通知 | 必测 | 必测 |
| 通知深链与反馈 | 必测 | 必测 |
| 断网、切网、恢复 | 必测 | 必测 |
| 重新登录与注销 | 必测 | 必测 |

## 6. 发布门槛

只有以下链路在真实手机上完成，才交给测试者持续使用：

```text
登录
-> chat
-> real model
-> memory write
-> relationship/state update
-> proactive decision
-> worker
-> phone notification
-> deep link
-> feedback
-> reboot
-> history/state restored
```

必须同时通过：

- 全量 backend/frontend/browser tests；
- 真实模型 smoke，检查响应内容而不仅是 HTTP 200；
- API/worker kill-restart；
- 本机重启恢复；
- 备份恢复；
- 72 小时 soak，无持续 worker 失败、重复通知或数据库锁；
- 一次 iPhone 与一次 Android 实机验收；
- export/delete、DND 和安全场景；
- public DTO 与日志泄漏扫描。

## 7. 实施顺序

1. P0-A 配置、独立数据目录和 SQLite 并发参数；
2. P0-B 登录、Cookie session 和同源边界；
3. P0-C systemd、release 目录、Tailscale HTTPS；
4. P0-D 健康、日志、备份恢复；
5. 用 Bark/Telegram 完成第一条真实主动通知闭环；
6. 真实手机执行 chat -> restart -> proactive -> feedback；
7. P1-A Web Push；
8. P1-B 版本更新和测试反馈；
9. 72 小时 soak 后再正式交付测试者。

第一交付点应放在第 6 步：此时已经可以进行小规模持续测试，Web Push 可在不阻塞第一轮关系质量测试的前提下继续完善。

## 8. 明确不做

- 不在本阶段支持多个互相隔离的注册用户；
- 不引入 Kubernetes、微服务或外部数据库；
- 不为部署改写 native ES Modules 前端；
- 不把 fixture、mock 或手机模拟器通过当成真实运行证明；
- 不在 HTTPS、认证、恢复和 DND 未通过前公开互联网访问；
- 不优先增加语音、头像、UGC 或新产品空间。
