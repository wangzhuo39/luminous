# S3 B7 Reminder / Calendar 验收证据

> 日期：2026-07-26
> 结论：通过
> 视觉基线：Crystal Solarium v2

## 覆盖范围

- Reminder“提醒光尘”混合列表、due/scheduled 层级与终态保留。
- Reminder 详情、精确 datetime snooze、取消内联确认。
- Calendar“窗框刻度”列表、定时与全天表单切换。
- Calendar 移出内联确认与 deleted 后再移除。
- 桌面 1440×900、移动 390×844、长标题、软键盘态与 reduced-motion。
- 控制台和 page error 为零，无横向溢出，可见触控目标至少 44px。

## 自动化结果

运行：

```bash
rtk node tests/frontend/s3-b7-browser-acceptance.mjs
```

结果：

```text
desktop-reminder-flow          passed  2 screenshots
desktop-calendar-flow          passed  3 screenshots
mobile-forms-reduced-motion    passed  2 screenshots
total                          passed  7 screenshots
```

全量 Node 回归：

```text
tests 156
pass 156
fail 0
```

## 截图

- `desktop-reminder-light-dust-list.png`
- `desktop-reminder-exact-snooze.png`
- `desktop-calendar-window-scale.png`
- `desktop-calendar-all-day-form.png`
- `desktop-calendar-remove-confirmation.png`
- `mobile-reminder-form-keyboard.png`
- `mobile-calendar-all-day-reduced-motion.png`

## Gemini 视觉过程与终审

初始视觉设计：

```text
/home/wz/gemini-api-traces/runs/20260726T072536.024453Z_luminous-b7-reminder-calendar-visual-v1_1381e473/
```

7 图多模态终审：

```text
/home/wz/gemini-api-traces/runs/20260726T074358.169906Z_luminous-b7-multimodal-audit-v1_8385810e/
```

Gemini 终审结果：总分 92，桌面 94，移动 89，隐喻契合 96；达到可交付，无 P0。终审提出的时间控件主题色、移动键盘留白、刻度可见度和确认按钮字重四项非阻塞 P1 已在本批修正，之后浏览器回归再次通过。

## 契约证据

- `tests/frontend/s3-reminder-calendar-b7.test.mjs` 覆盖安全 ViewModel、排序、终态编辑门禁、精确 snooze、取消 POST 语义、全天转换、非法结束与保守删除。
- Reminder cancel 不使用 DELETE；cancelled 项不消失。
- Calendar 不调用单项 GET；只有 `status=deleted` 的删除响应能移出列表。
- 表单时间经本地严格 round-trip 转为 UTC `Z`，时区取浏览器 IANA 名称并回退 UTC。
