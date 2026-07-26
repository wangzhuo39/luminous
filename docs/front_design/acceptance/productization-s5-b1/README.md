# S5 产品化验收证据

## 覆盖场景

1. `desktop-deep-link-draft-recovered.png`：`?space=privacy` 打开/关闭/back，刷新后恢复 session draft；
2. `desktop-install-eligible.png`：安装资格事件前隐藏、事件后在隐私页完整可见，离线能力文案诚实；
3. `mobile-offline-shell.png`：390×844、reduced-motion、API 模式、Service Worker 接管后完全断网刷新；对话隐藏、发送禁用、静态温室可见。

## 自动化结果

```text
Node: 175/175
S5 Chromium: 3 scenarios / 3 screenshots
跨阶段 Chromium: 9/9 scripts PASS
Gemini 复审: 98/100，无 P0/P1/P2，可以关闭 S5
```

## Gemini traces

```text
/home/wz/gemini-api-traces/20260726T092553.454804Z_luminous-s5-productization-experience-design-v1_ff1a36e1/
/home/wz/gemini-api-traces/20260726T094147.682350Z_luminous-s5-productization-multimodal-audit-v1_5afb712e/
/home/wz/gemini-api-traces/20260726T095758.931820Z_luminous-s5-productization-multimodal-reaudit-v1_33b50445/
```

每个目录均保留完整 request、输入图片副本、raw response、assistant text、manifest 和失败/成功状态。三次调用均主接口首试成功；初审问题经过代码、截图和专项断言修复后才复审。
