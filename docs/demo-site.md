# 在线演示与媒体复现

[公开展厅](https://hwfengcs.github.io/DM-Code-Agent/) 是从公开 fixture 生成的静态站点。
它展示可点击的报告，不启动 agent、不连接模型，也不开放服务器命令执行接口。
完整本地工作台见 [Web 控制台](web.md)。

## 构建

在仓库根目录运行，输出路径必须是新目录或空目录：

```bash
uv sync --frozen --extra dev
uv run --frozen python scripts/build_demo_site.py --output build/site
python -m http.server 8876 --bind 127.0.0.1 --directory build/site
```

脚本用 `dm_agent.demo.run_demo` 运行两次真实工具流程，原始 trace、工作区、补丁和
清单留在 `build/site-source/`，仅把已审阅的公开 fixture 和派生 HTML 放进 `build/site/`。
输出目录不能包含原始目录，反之亦然。重建时选用新输出目录；原始日志不会被清理或覆盖。

发布目录包含两份报告、固定源代码/测试/补丁，以及带 SHA-256 的
`demo-manifest.json`。不复制 JSONL、checkpoint、用户会话或环境变量。
`.github/workflows/pages.yml` 在 main 更新后构建并发布到 GitHub Pages。

## 截图与 38 秒操作录屏

`docs/media/demo-preview.png` 和 `social-preview.png` 来自真实生成的页面。
`demo-walkthrough.gif` / `demo-walkthrough.mp4` 是 Playwright 操作该页面的浏览器录屏，
字幕说明来源；没有伪造模型响应或终端输出。案例中的模型决策是脚本，文件编辑和 unittest
确实执行。视频没有声音，GIF 和 MP4 展示同一流程。

复现需要 Chrome、Node.js、FFmpeg（在 PATH 中），以及 Playwright 1.59.1：

```bash
npm install --prefix build/media-tools playwright@1.59.1
npx --prefix build/media-tools playwright install ffmpeg
```

然后设置 `PLAYWRIGHT_MODULE` 为
`build/media-tools/node_modules/playwright/index.mjs` 的**绝对路径**，运行：

```bash
node scripts/capture_demo.mjs --record
```

脚本默认访问 `http://127.0.0.1:8876/`，可以用 `DEMO_URL` 指向另一个本地构建地址。
默认用 Chrome，也可通过 `BROWSER_CHANNEL` 指定 Playwright 支持的浏览器通道。
省略 `--record` 时只做截图与浏览器检查；媒体文件会被更新，原始录屏保留在
`build/media-capture/`。桌面/手机截图和交互检查结果也保存在该目录。

检查包括两种报告切换、链接和按钮状态、页面横向溢出、加载错误，以及单文件报告无额外请求。
发布前还需目视检查截图和录屏帧，确认文字可读、测试证据与 fixture 一致。
