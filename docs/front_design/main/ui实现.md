这类 UI **不应该强行全部用 CSS 画出来**。AI 设计图里的晶体图标、复杂花纹边框、星光折射，本质上更接近游戏 UI 或视觉小说 UI，正确做法是：

> **图片负责复杂美术，SVG 负责可缩放图标和线框，CSS 负责布局与材质，Canvas 负责粒子和动态。**

这样才能同时还原视觉、保持响应式，并让文字和状态仍然动态更新。

---

# 一、推荐采用混合实现方案

| 内容            | 实现方式              |
| ------------- | ----------------- |
| 人物与场景         | WebP / AVIF 背景图   |
| 今日、记忆、来信、心迹图标 | 独立 SVG            |
| 状态栏复杂花纹框      | SVG 框架或分片 PNG     |
| 状态栏文字与数值      | HTML              |
| 玻璃模糊、阴影、高光    | CSS               |
| 水面反射、微弱噪点     | PNG/WebP 纹理 + CSS |
| 星尘、雨滴、漂浮光点    | Canvas            |
| 图标环绕光点        | CSS/SVG 动画        |
| 点击水波          | CSS 或 Canvas      |
| 对话内容          | HTML 局部滚动区        |

不要选择下面两种极端方案：

* **全部切成一张大图**：文字不能动态更新，响应式困难。
* **全部用 CSS 手画**：复杂图标和装饰框成本很高，还原度低。

---

# 二、先把设计图拆成“美术资产”和“动态内容”

你的主页面可以拆成以下图层：

```text
Layer 0  深蓝底色
Layer 1  人物背景图
Layer 2  远景星尘 Canvas
Layer 3  人物前景光点 Canvas
Layer 4  顶部时间和角色信息
Layer 5  四个 SVG 悬浮图标
Layer 6  滚动式对话文字
Layer 7  状态栏 SVG 装饰框
Layer 8  状态栏 HTML 内容
Layer 9  输入框和发送按钮
Layer 10 点击涟漪与流光
```

建议资产目录：

```text
assets/
├─ backgrounds/
│  ├─ yezhen-home.avif
│  ├─ yezhen-home.webp
│  └─ yezhen-home-small.webp
│
├─ icons/
│  ├─ today.svg
│  ├─ memory.svg
│  ├─ letter.svg
│  ├─ heart-trace.svg
│  ├─ heartbeat.svg
│  ├─ rain.svg
│  └─ quiet-moon.svg
│
├─ frames/
│  ├─ status-left.svg
│  ├─ status-center.svg
│  ├─ status-right.svg
│  ├─ input-left.svg
│  └─ input-right.svg
│
├─ textures/
│  ├─ glass-noise.webp
│  ├─ water-caustics.webp
│  ├─ soft-glow.webp
│  └─ foreground-bokeh.webp
│
└─ masks/
   ├─ jewel-mask.webp
   └─ character-light-mask.webp
```

你已经有一张去掉组件的人物背景图，这正好作为 `yezhen-home.webp` 使用。

---

# 三、漂亮图标不要从完整设计图里直接裁切

从 UI 设计图裁切图标虽然最快，但存在几个问题：

* 背景不透明；
* 尺寸变化后模糊；
* 四周会残留背景颜色；
* 发光无法根据交互动态变化；
* 不容易适配不同分辨率。

更合理的是为每个入口制作一张独立 SVG。

## 图标的结构

以“记忆晶体”为例：

```html
<button class="floating-entry" aria-label="打开共同记忆">
  <span class="icon-orbit" aria-hidden="true"></span>

  <svg class="entry-icon" viewBox="0 0 80 80" aria-hidden="true">
    <defs>
      <linearGradient id="crystal-fill" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#eef8ff" stop-opacity=".9" />
        <stop offset="45%" stop-color="#8bc8ff" stop-opacity=".7" />
        <stop offset="100%" stop-color="#4366bb" stop-opacity=".45" />
      </linearGradient>

      <filter id="crystal-glow" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="2.5" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <circle
      cx="40"
      cy="40"
      r="34"
      fill="rgba(20, 46, 79, .28)"
      stroke="rgba(190, 224, 255, .55)"
    />

    <path
      d="M40 17 L55 37 L47 61 L31 61 L24 37 Z"
      fill="url(#crystal-fill)"
      stroke="#d8efff"
      filter="url(#crystal-glow)"
    />
  </svg>

  <span class="entry-label">记忆</span>
</button>
```

这里 SVG 负责：

* 晶体形状；
* 渐变；
* 描边；
* 内部高光；
* 基础发光。

CSS 负责：

* 整体悬浮；
* 轨道旋转；
* 点击反馈；
* 未读提示；
* 外部光晕。

```css
.floating-entry {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 8px;
  width: 72px;
  border: 0;
  color: #edf5fb;
  background: none;
  cursor: pointer;
}

.entry-icon {
  width: 58px;
  height: 58px;
  overflow: visible;
  filter:
    drop-shadow(0 0 7px rgba(132, 195, 255, 0.45))
    drop-shadow(0 8px 18px rgba(0, 8, 24, 0.45));
  animation: icon-float 7s ease-in-out infinite;
}

.icon-orbit {
  position: absolute;
  top: -2px;
  width: 62px;
  height: 62px;
  border: 1px solid rgba(193, 224, 255, 0.25);
  border-radius: 50%;
  animation: orbit 10s linear infinite;
}

.icon-orbit::after {
  content: "";
  position: absolute;
  top: -3px;
  left: calc(50% - 3px);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ebd4ac;
  box-shadow:
    0 0 6px #ebd4ac,
    0 0 16px rgba(235, 212, 172, 0.75);
}

@keyframes icon-float {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-4px);
  }
}

@keyframes orbit {
  to {
    transform: rotate(360deg);
  }
}
```

四个图标最好分别制作，不要用同一个图标简单换图形。这样才能接近游戏 UI 的精细程度。

---

# 四、复杂状态栏不要用一整张不可缩放图片

设计图里的状态框有：

* 两端尖角；
* 银色边框；
* 中间晶体；
* 多层内框；
* 外部流光；
* 玻璃底色。

如果把整条状态框做成一张 PNG，一旦改变宽度，左右装饰和中间晶体就会变形。

推荐使用**三段式框架**：

```text
左侧固定装饰 | 中间可拉伸区域 | 右侧固定装饰
                    +
                中央晶体
```

HTML：

```html
<section class="status-panel">
  <div class="status-frame" aria-hidden="true">
    <img class="frame-cap frame-cap-left" src="/assets/frames/status-left.svg">
    <div class="frame-middle"></div>
    <img class="frame-cap frame-cap-right" src="/assets/frames/status-right.svg">
    <img class="frame-jewel" src="/assets/frames/status-center.svg">
  </div>

  <div class="status-content">
    <!-- 动态 HTML 内容 -->
  </div>
</section>
```

CSS：

```css
.status-panel {
  position: relative;
  min-height: 104px;
  margin-inline: 22px;
  isolation: isolate;
}

.status-frame {
  position: absolute;
  inset: 0;
  z-index: -1;
  display: grid;
  grid-template-columns: 74px 1fr 74px;
  pointer-events: none;
}

.frame-cap {
  width: 74px;
  height: 100%;
  object-fit: fill;
}

.frame-middle {
  border-block:
    1px solid rgba(213, 230, 246, 0.48);
  background:
    linear-gradient(
      180deg,
      rgba(40, 65, 101, 0.66),
      rgba(11, 27, 49, 0.72)
    );
  box-shadow:
    inset 0 1px rgba(255, 255, 255, 0.12),
    inset 0 -1px rgba(125, 181, 232, 0.12),
    0 18px 44px rgba(0, 5, 18, 0.38);
  backdrop-filter: blur(18px) saturate(125%);
}

.frame-jewel {
  position: absolute;
  top: -15px;
  left: 50%;
  width: 44px;
  transform: translateX(-50%);
  filter: drop-shadow(0 0 12px rgba(133, 197, 255, 0.6));
}

.status-content {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: center;
  min-height: 104px;
  padding: 18px 72px;
}
```

这种方法的优势：

* 左右装饰不会拉伸；
* 中间部分可以响应式扩展；
* 中央晶体保持原比例；
* 文字仍然是真实 HTML；
* 状态内容可以实时变化。

---

# 五、另一种方案：使用 SVG 作为完整外框

也可以把状态框制作成一个完整 SVG，但不要让整个 SVG 使用：

```html
preserveAspectRatio="none"
```

否则两端花纹会被横向拉长。

更好的 SVG 结构是：

```svg
<svg viewBox="0 0 900 120">
  <defs>
    <!-- 渐变、滤镜 -->
  </defs>

  <!-- 可变宽中间线 -->
  <path d="M70 4 H830" />

  <!-- 固定左装饰 -->
  <g id="left-cap">...</g>

  <!-- 固定右装饰 -->
  <g id="right-cap">...</g>

  <!-- 固定中央晶体 -->
  <g id="center-jewel">...</g>
</svg>
```

但如果面板宽度需要大范围变化，三段式通常更容易控制。

---

# 六、玻璃感主要由 CSS 完成

复杂花纹交给 SVG，面板玻璃感交给 CSS：

```css
.glass-panel {
  background:
    linear-gradient(
      155deg,
      rgba(72, 101, 140, 0.22),
      rgba(9, 22, 42, 0.72)
    );

  border: 1px solid rgba(196, 221, 243, 0.26);

  backdrop-filter:
    blur(18px)
    saturate(125%);

  box-shadow:
    0 20px 50px rgba(0, 5, 18, 0.42),
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    inset 0 -1px 0 rgba(92, 157, 220, 0.1);
}
```

加入微弱纹理，能避免玻璃区域显得过于“网页组件化”：

```css
.glass-panel::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0.035;
  background-image: url("/assets/textures/glass-noise.webp");
  background-size: 180px;
  mix-blend-mode: screen;
}
```

---

# 七、状态图标也应该是独立 SVG

状态栏内部的：

* 心跳球；
* 雨伞球；
* 月相球；

不要作为状态栏背景的一部分烘焙进去。每个状态项都应该是独立 SVG，以便更换状态和执行动画。

```html
<article class="status-item">
  <span class="status-icon-shell status-heartbeat">
    <img src="/assets/icons/heartbeat.svg" alt="">
  </span>

  <div>
    <strong>心跳平稳</strong>
    <small>72 次/分</small>
  </div>
</article>
```

```css
.status-icon-shell {
  display: grid;
  place-items: center;
  width: 48px;
  aspect-ratio: 1;
  border-radius: 50%;
  background:
    radial-gradient(
      circle at 42% 32%,
      rgba(213, 238, 255, 0.26),
      rgba(40, 75, 119, 0.18) 44%,
      rgba(5, 18, 37, 0.5) 100%
    );
  box-shadow:
    inset 0 0 14px rgba(163, 213, 255, 0.13),
    0 0 16px rgba(101, 169, 229, 0.18);
}
```

心跳动画只动图标，不动整个状态项：

```css
.status-heartbeat img {
  animation: heartbeat 3.6s ease-in-out infinite;
}

@keyframes heartbeat {
  0%,
  68%,
  100% {
    transform: scale(1);
  }

  73% {
    transform: scale(1.08);
  }

  78% {
    transform: scale(0.99);
  }

  83% {
    transform: scale(1.05);
  }
}
```

---

# 八、发光边框可以使用 CSS Mask

输入框聚焦后的流光，不需要准备很多图片：

```css
.input-shell {
  position: relative;
  border-radius: 32px;
}

.input-shell::before {
  content: "";
  position: absolute;
  inset: -1px;
  padding: 1px;
  border-radius: inherit;
  pointer-events: none;

  background:
    linear-gradient(
      110deg,
      transparent 20%,
      rgba(181, 221, 255, 0.8) 48%,
      transparent 72%
    );
  background-size: 220% 100%;

  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;

  mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  mask-composite: exclude;

  opacity: 0;
}

.input-shell:focus-within::before {
  opacity: 1;
  animation: border-flow 3s linear infinite;
}

@keyframes border-flow {
  to {
    background-position: -220% 0;
  }
}
```

这适合 Chromium，也正好符合你使用 Chrome / Playwright 验收的环境。

---

# 九、粒子效果用 Canvas，不要创建大量 DOM

对于星尘、光点、雨滴，建议页面上只放一个：

```html
<canvas id="particle-layer"></canvas>
```

基础结构：

```js
const canvas = document.querySelector("#particle-layer");
const ctx = canvas.getContext("2d");

const particles = [];

function resizeCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = window.innerWidth * dpr;
  canvas.height = window.innerHeight * dpr;
  canvas.style.width = `${window.innerWidth}px`;
  canvas.style.height = `${window.innerHeight}px`;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function createParticle() {
  return {
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    radius: 0.5 + Math.random() * 2,
    speedX: -0.03 + Math.random() * 0.06,
    speedY: -0.08 - Math.random() * 0.12,
    opacity: 0.1 + Math.random() * 0.35,
    phase: Math.random() * Math.PI * 2,
  };
}

for (let i = 0; i < 45; i += 1) {
  particles.push(createParticle());
}

function render(time) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

  for (const particle of particles) {
    particle.x += particle.speedX;
    particle.y += particle.speedY;

    if (particle.y < -10) {
      Object.assign(particle, createParticle(), {
        y: window.innerHeight + 10,
      });
    }

    const flicker =
      0.78 + Math.sin(time * 0.001 + particle.phase) * 0.22;

    ctx.globalAlpha = particle.opacity * flicker;
    ctx.fillStyle = "#b9dcff";
    ctx.beginPath();
    ctx.arc(
      particle.x,
      particle.y,
      particle.radius,
      0,
      Math.PI * 2
    );
    ctx.fill();
  }

  requestAnimationFrame(render);
}

resizeCanvas();
window.addEventListener("resize", resizeCanvas);
requestAnimationFrame(render);
```

Canvas 放在人物前还是人物后，由 `z-index` 决定。建议使用两个 Canvas：

```text
background-particles   人物后面
foreground-particles   人物前面，但避开面部
```

---

# 十、生成式设计图中的细节如何变成真实资产

这里才是还原度的关键。

## 方法一：人工在 Figma 中重绘

适合：

* 外框；
* 简单月相；
* 信封；
* 晶体；
* 莲花；
* 轨道圆环。

流程：

1. 把设计图放入 Figma；
2. 锁定为参考层；
3. 使用 Pen、Ellipse 和 Gradient 重绘；
4. 使用多层描边和模糊制作发光；
5. 导出 SVG；
6. 删除 SVG 中不必要的固定宽高；
7. 保留 `viewBox`。

这是最稳定的生产方式。

## 方法二：让图像模型单独生成资产

不是让模型生成整张 UI，而是分别生成：

```text
isolated fantasy crystal memory icon,
transparent background,
symmetrical,
front-facing,
game UI asset,
no text,
no surrounding panel
```

然后：

1. 去背景；
2. 转 PNG；
3. 必要时使用矢量描摹；
4. 手工清理；
5. 统一尺寸与光线方向。

这种方式更快，但最终仍然需要人工整理。

## 方法三：从设计图裁切，用作临时原型

只适合快速验证：

* 裁出图标；
* 清除背景；
* 导出透明 PNG；
* 页面中用 `<img>` 显示。

等布局和交互确认后，再替换成 SVG 或高质量独立资产。

---

# 十一、推荐你按两个阶段实施

## 第一阶段：先把设计还原出来

先不追求所有东西都是真正矢量：

* 人物：WebP
* 图标：透明 PNG
* 装饰框：三段式 PNG
* 玻璃：CSS
* 文字：HTML
* 粒子：Canvas

这样最快能达到设计图 **80%–90% 的视觉效果**。

## 第二阶段：把关键资产精细化

再逐步替换：

* 入口 PNG → SVG
* 状态图标 PNG → SVG
* 状态框 PNG → SVG 分片
* 静态高光 → CSS/SVG 动画
* 固定粒子 → Canvas 动态粒子

不要一开始就试图把所有细节都工程化，否则会卡在美术资产制作上。

---

# 十二、最适合你当前项目的技术结构

你现在是原生 ES Modules 项目，不需要为了这个页面立刻迁移 React。可以这样组织：

```text
companion-ui/
├─ index.html
├─ styles/
│  ├─ tokens.css
│  ├─ layout.css
│  ├─ components.css
│  └─ effects.css
│
├─ scripts/
│  ├─ app.js
│  ├─ particles.js
│  ├─ parallax.js
│  ├─ conversation-stream.js
│  └─ effects-controller.js
│
└─ assets/
   ├─ backgrounds/
   ├─ icons/
   ├─ frames/
   └─ textures/
```

主页面组件可以直接用 Web Components 或工厂函数：

```js
export function createFloatingEntry({
  label,
  icon,
  href,
  unread = false,
}) {
  const element = document.createElement("a");

  element.className = "floating-entry";
  element.href = href;
  element.setAttribute("aria-label", `打开${label}`);

  element.innerHTML = `
    <span class="icon-orbit"></span>
    <span class="entry-icon-shell">
      <img src="${icon}" alt="">
      ${unread ? '<span class="unread-dot"></span>' : ""}
    </span>
    <span class="entry-label">${label}</span>
  `;

  return element;
}
```

没有框架也完全可以实现。

---

# 最重要的结论

这张主页面的高还原方案不是“寻找更复杂的 CSS”，而是建立一套小型的**游戏 UI 资产管线**：

1. 人物和场景使用高质量位图；
2. 图标和边框制作成独立透明资产；
3. 状态文字和对话使用 HTML；
4. 玻璃和流光使用 CSS；
5. 星尘和雨滴使用 Canvas；
6. 所有装饰与内容分层；
7. 复杂框架使用三段式或九宫格式缩放。

这样既能接近设计图，也不会失去动态数据、响应式和交互能力。
