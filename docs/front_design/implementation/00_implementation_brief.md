# 00 Implementation Brief

## 当前目标

把现有静态前端：

`/home/wz/luminous/apps/companion-web/companion-ui/index.html`

从“三栏工具台”重构为「晶格温室 The Crystal Solarium」沉浸式伴侣空间。

## 技术栈

- Vanilla HTML/CSS/JS
- Python 后端静态托管
- 无 React
- 无 Vite
- 无 package.json
- 首轮不新增构建链路

## 启动方式

```bash
luminous-api --host 127.0.0.1 --port 8000 --mock
```

访问：

```text
http://127.0.0.1:8000
```

## Gemini 输出格式

实现阶段每次只请求一个 batch。

优先要求 Gemini 输出：

1. unified diff patch；或
2. 完整替换后的 `index.html`。

不要接受：

- 伪代码
- 只描述不落代码
- 多文件架构迁移但没有落地补丁
- 引入 React/Vite/Tailwind/外部依赖

## Codex 验收职责

Gemini 产出后，Codex 必须：

- 应用补丁
- 检查 `index.html`
- 启动 mock 服务
- 浏览器查看桌面与 390x844 移动端
- 检查 DOM 中没有 `system_thinking`
- 验证核心 API 行为没有被删
- 修复 Gemini 的集成问题
