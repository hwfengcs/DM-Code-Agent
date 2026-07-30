# Web 控制台

`dm-agent-web` 提供一套浏览器界面，做两件事：

1. **本地工作台** — 发起任务、看实时步骤、审计会话、从任意一步分叉重跑。
2. **只读展厅** — 不需要 API key、可静态托管的会话查看器，用来把项目讲给别人看。

这两件事**共用一套渲染器**，因为 live run 与历史 trace 是同一份 append-only JSONL
条目流。没有第二套数据模型，也不可能出现「实时看到的」与「事后审计到的」不一致。

```bash
uv sync --frozen --extra dev          # dev extra 自引用 web extra，一条装齐
# 或：pip install 'dm-code-agent[web]'

dm-agent-web --read-only              # 只读展厅：只能审计，不能发起运行
dm-agent-web                          # 完整工作台
```

启动后终端会打印一条**带 token 的地址**，直接点开即可：

```
DM-Code-Agent Web Console
  模式      只读展厅
  鉴权      token 已启用
  workspace C:\path\to\your\repo
  sessions  C:\path\to\your\repo\sessions
  打开      http://127.0.0.1:8765/?token=xxxxxxxx
```

前端会把 token 存进 `sessionStorage` 并**从地址栏抹掉**，免得它留在截图和浏览器
历史里。丢了 token 就重启一次，或用 `--token` 指定一个固定值。

## 开关

| 开关 | 默认 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 监听地址。**非 loopback 地址强制要求 token**，否则拒绝启动 |
| `--port` | `8765` | 监听端口 |
| `--sessions-dir` | `sessions` | 会话 JSONL 所在目录，控制台只读写这个目录内的文件 |
| `--workspace` | `.` | agent 的工作目录。非只读模式下它会在这里**真实读写文件** |
| `--read-only` | 关 | 只提供审计能力，禁用发起运行与分叉。公开分享用这个 |
| `--token` | 自动生成 | 固定访问 token；省略时生成一个一次性的 |
| `--no-token` | 关 | 关闭鉴权。只允许用于 loopback，且不推荐 |
| `--static-dir` | 随包产物 | 前端产物目录，一般不用指定 |

## 五个视图

| 视图 | 回答什么问题 |
| --- | --- |
| **会话库** | 哪些跑成功了，以及**哪些跑成功了但过程不健康** |
| **运行详情** | 这次运行每一步做了什么；选中条目看它的完整 payload |
| **诊断** | 失败在哪个阶段、有没有恢复、**有没有跳过验证**、有没有幻觉信号 |
| **折叠** | 折叠省了多少 token，以及被跳过的原文——它们**一条都没删** |
| **行为 diff** | 两次运行从第几步开始分道扬镳 |

会话库刻意把「状态」和「过程健康」分成两列，并单独统计「成功但不健康」的数量。
这是本项目的核心主张：**任务成功 ≠ 过程健康**，而后者是能被机器读出来的。

诊断视图渲染的是 `dm_agent.tracing.analyze_events` 的输出，与
`dm-agent-trace analyze` **完全同源**——`tests/test_server_readonly.py` 有一条断言
逐字段比对 API 响应与直接调用纯函数的结果，防止 server 层自己算一遍导致漂移。

## 安全模型

本地跑一个能改你代码、能执行命令的服务，边界必须清楚：

| 措施 | 实现 |
| --- | --- |
| 默认只对本机可见 | 绑 `127.0.0.1` |
| 非 loopback 必须有 token | 在构造 `ServerSettings` 时就 fail closed，不是起来再说 |
| token 常数时间比较 | `secrets.compare_digest`，不按字节提前返回 |
| 路径不可穿越 | `resolve_session_path` 是唯一入口，四道检查：后缀、绝对路径、解析后越界、存在性 |
| 只读模式无写路径 | 发起运行、分叉一律 403 |
| 无命令注入 | argv 由白名单拼装、`shell=False`、任务文本作为**单个** argv 元素放在 `--` 之后 |
| 数值参数不静默截断 | 超范围直接 400 |
| 不泄露绝对路径 | 会话相关响应只含相对名 |
| 不泄露 API key | `/api/meta` 只回报某个 key **配没配**，不回报值 |
| 关停不留孤儿 | lifespan 收掉在跑的子进程树 |

对应测试：`tests/test_server_security.py`、`tests/test_server_process.py`。

**它不是给公网部署的。** 要给别人看，用下面的静态托管方式，而不是把这个服务暴露出去。

## 为什么运行走子进程

`POST /api/runs` spawn 一个 `python -m dm_agent.cli` 子进程，而不是在服务进程里直接
构造 `ReactAgent`。四个理由，最后一条最重要：

| | 子进程（选定） | 进程内 |
| --- | --- | --- |
| 取消运行 | `terminate()` 即可 | `ReactAgent` **没有取消接口**，钩子抛异常按文档等价于放行，需要改内核 |
| MCP stdio 子进程 | 随 agent 进程一起收掉 | 得自己管 |
| 崩溃隔离 | 不影响控制台 | 可能拖垮控制台 |
| **与 CLI 的一致性** | **Web 是 CLI 的前端，不会漂移** | 事实上的第二套装配逻辑 |

代价是每次启动约 1–2s 进程开销，配置只能经 argv 传递。这个代价换来的是「控制台永远
和 CLI 做同一件事」，值得。

`tests/test_server_process.py` 有一条断言把生成的 argv 直接喂给 `dm_agent.cli` 真正的
解析器——有人改了 CLI 开关名而忘了改这边，测试立刻红，而不是等运行时报
`unrecognized arguments`。

## 实时流

SSE，数据源就是会话日志本身（`TraceWriter.record()` 每条都 `flush`）：

- `event: status` — 连上时先给一次当前状态
- `event: entry` — 每条会话条目，`id:` 是它在文件里的**行号**
- `event: malformed` — 某行解析不了，跳过但报出来
- `event: done` — 运行结束，附终态

行号能当续传游标，正是因为会话日志 append-only、行号永不变动。浏览器断线重连时自动
带上 `Last-Event-ID`，服务端据此跳过已发送的行。写侧虽然是「整行 + flush」，读侧仍
可能撞上半行——只有收到换行才会发出，否则前端会拿到解析不了的 JSON。

## 运行状态的口径

**退出码 0 不等于 agent 做完了。** `dm-agent` 对 `max_steps_exceeded` 也返回 0
（那不算 CLI 失败，只是 agent 没做完）。所以控制台同时读会话日志 `run_end` 里 agent
自己判定的状态：

| 状态 | 含义 |
| --- | --- |
| `running` | 子进程还在跑 |
| `completed` | 退出码 0 **且** agent 报了 success |
| `incomplete` | 退出码 0，但 agent 没宣布成功（步数耗尽、被完成门否决等） |
| `failed` | 子进程非零退出 |
| `cancelled` | 被用户停止（**已写入的会话日志保留**，它同样是证据） |

## 静态托管（拿去传播）

前端用 hash 路由、`base: './'`，所以同一份构建既能被 uvicorn 挂在 `/` 下，也能直接
静态托管。把会话 JSONL 和构建产物一起放上去即可：

```bash
npm --prefix web run build      # 产物落到 dm_agent/server/static/
```

只读展厅不需要 API key，也不需要后端——这是把项目讲清楚最省事的方式。

## 前端开发

```bash
npm --prefix web install
npm --prefix web run dev        # 5173，/api 代理到 8765
npm --prefix web run test       # vitest，覆盖展示层纯函数
npm --prefix web run build      # tsc --noEmit && vite build
```

产物 `dm_agent/server/static/` **入库**，因为 `pip install dm-code-agent[web]` 之后
必须直接就有界面，不能要求终端用户装 Node 再构建。改了 `web/` 下的源码请重新
`npm run build` 并把产物一起提交。

**前端不算任何结论。** 失败阶段、健康度、验证缺口、行为 diff 全部由后端的
`dm_agent.tracing` 算好送过来，前端只做分组、归类、格式化。这条边界是刻意的：
一旦前端开始自己判断，就有了第二套实现，两边迟早漂移。

## 分层位置

```
clients → tools → tracing → core → extensions → cli
                                              ↘ server
```

`dm_agent/server/` 与 `dm_agent/cli/` 同级，都是最外层装配者：可以依赖任何下层，
但 **server 不得 import cli**（它 spawn CLI 子进程，不把 CLI 当库用），也没有任何
下层可以反向依赖 server。

这三条 ruff 的 `TID251` 拦不住——`dm_agent/server/**` 为了能写 `from .settings import`
必须整体豁免 TID251（同 `dm_agent/cli/**`），豁免之后 server → cli 也就不报错了。
所以它们改由 `tests/test_server_layering.py` 用 AST 静态断言。

核心包**不依赖任何 web 框架**：不装 `[web]` extra 时 `import dm_agent` 与全部 CLI
功能不受影响，只有 `dm-agent-web` 会打印一条能照着敲的安装提示。
