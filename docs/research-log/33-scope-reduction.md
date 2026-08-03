# 33 · 减法重构：删掉无法被证伪的东西

- 日期：2026-08-03
- 分支：`refactor/scope-reduction`
- 相关：[01](01-swebench-baseline.md) [02](02-reflexion.md)
  [04](04-critic-and-consistency.md) [22](22-repeated-failure-policy-experiment.md)
  [24](24-memory-hygiene-and-recall.md) [27](27-tool-circuit-breaker-experiment.md)

## 为什么

起因是一个主观感受："代码有些冗余，好多没啥用，对性能不提升。"

先做了实证核查，结论出人意料：**全仓几乎没有传统死代码**。对 `dm_agent/` 做 AST 扫描，
所有公开定义的函数/类里只有 1 个（`memory/context_budget.py` 的 `last_write_step`，
2 行）完全无引用；另外 23 个"无引用"是 FastAPI 路由装饰器的误报。

所以冗余不在符号层，在**架构层**——有整个子系统存在、有测试、有文档，却产生不了价值。
根因是一条断链：

1. `docs/project-status.md` 冻结了真实评测；
2. 而 devlog 22 与 27 的 "promotion bar" 明确写着需要 live 数据支撑；
3. **验证这些模块的唯一手段被冻结了 ⇒ 它们永远无法毕业。**

这批代码卡在"实现完成、keyless 测试全绿、但永远无法被证明有效"的状态。留着它们的代价
不是磁盘，是每次改内核都要照顾的分支、每次读文档都要绕过的段落、以及一份 35 个开关的
CLI——其中大部分用户永远不该打开。

同时发现一件被埋没的事：**能出分的评测一直都在**。`dm_agent/benchmarks` 的
coding + maintenance suite 共 13 题，本地建工作区 → agent 改代码 → 加隐藏测试 →
pytest 判 pass/fail，产出 `overall_pass_rate`。历史报告 `bench_reports/deepseek_coding.json`
实测 DeepSeek **pass_rate 0.5（3/6）**。对比 SWE-bench Lite 的 0.0% resolved——
能用的那个被跑不通的那个盖住了。

## 删了什么

| 批次 | 内容 | 净删除 |
| --- | --- | --- |
| 1 | SWE-bench Lite 子系统（含 202 行 CLI 胶水、`swebench` extra 与 26 个传递依赖） | ~4100 行 |
| 2 | Reflexion / Critic / Self-Consistency | ~2380 行 |
| 3 | 工具熔断、repeated-failure 策略实验、`--enable-evolution`、记忆卫生、LLM 摘要压缩、`extensions/capabilities/` 子包 | ~1040 行 |
| 4 | 唯一的真死代码、两个薄包装器、一份腐化的任务清单副本、误建目录 | ~200 行 |

`dm-agent` CLI 开关 **35 → 23**。删 `swebench` extra 顺带让 `uv.lock` 少了 1393 行
（`datasets` 拖来的 pyarrow / fsspec / aiohttp 全家桶）。

## 边界：什么该留下

减法最大的风险是删过头。三条判据：

**1. 通用机制不随其唯一使用者一起删。**
`CompletionGate` 不依赖 Critic——Critic 只是挂在 `before_finish` 上的一个处理器，
钩子链为空即放行。同理 `run()` 的多 attempt 编排是通用的 `on_run_end` 重试机制，
ReflexionLoop 只是它的使用者之一。两者都保留。

被否决时的 `error_kind="critic_rejected"` 也保留：它是完成门否决的历史字段名，
会话日志与 planner 的重规划策略都按它对齐。改名的收益不抵破坏历史 trace 兼容的代价。

**2. 读侧兼容优先于整洁。**
`sessions/` 里的历史会话确实含 `critic_enabled` / `critic_review_count` /
`reflexion_lesson_count` 等字段。`tracing/analysis.py` 的 critic 失败分类与前端
`entries.ts` 的 `critic_review` 渲染**全部保留**——删了就等于让老 trace 读不了，
那直接违背"可审计、可回放"这条立身之本。只删写侧（`writer.record_critic_review`）。

**3. 公开导出的独立组件保留其能力参数。**
`Mem0StyleMemory` 是 `dm_agent/__init__.py` 的公开导出，第三方可以直接用它并传
`invalidate_on_success=True`。所以 memory 层的这个参数保留，只删 compressor 侧的
`enable_hygiene` 开关传递；对应测试改为直接测 memory 层，覆盖不减。

## 意外收益

- **删 Reflexion 解掉三条限制**：`--conversation-stdin` 不再需要拒绝它、
  `--checkpoint/--resume` 不再与它互斥、server 的 `RunSpec.validate` 对话模式特判与
  前端 `Chat.tsx` 的开关过滤一并消失。两个 server argv 测试原本要
  `if key != "enable_reflexion"` 排除它，现在直接用全量开关集合，**覆盖反而更强**。
- **内置能力清零 ⇒ 过渡层消失**：熔断是最后一个内置能力，删掉后
  `builtin_capabilities_for()` 永远返回空，那层"把旧开关翻译成内置能力"的代码失去意义，
  `ReactAgent(capabilities=[...])` 成为可选能力的唯一入口。这是内核最小化的又一步。

## 怎么验证的

删的**全部是默认关闭的模块**，所以默认路径行为必须逐字节不变——这是把"删功能"降级成
"可验证重构"的关键。每批次都跑：

1. `pytest`（427 passed）
2. `dm_agent.evals.cli` 全 56 runs，与删除前**逐字段对比**
3. `compileall` / `ruff` / `black` / `mypy` / `uv lock --check`
4. 两条 benchmark manifest 签名（CI 同款 `manifest_diff`）
5. **历史 trace 可读性**：对含 `critic_*` / `reflexion_*` 字段的老会话跑 `analyze` 与 `view`
6. 前端 typecheck + 38 个测试 + 产物重建比对

eval 对比结果是这次减法最有力的证据——累计只有 **15 个 metadata 键被移除**
（全部属于已删功能），**无新增键、无任何键值变化**，summary 逐字段一致、
`overall_success_rate` 保持 1.0：

```
critic_enabled / critic_fail_count / critic_pass_count / critic_reject_count /
critic_review_count / reflexion_enabled / reflexion_lesson_count / max_trials /
circuit_breaker_enabled / circuit_breaker_block_count / circuit_breaker_trip_count /
memory_hygiene_enabled / llm_compression_enabled /
repeated_failure_policy_experiment_enabled / repeated_failure_policy_applied_count
```

对比时需剔除 `duration_seconds` 与 `backup_dir` 两个天然非确定性字段（墙钟计时、
随机临时目录）。

## 顺带记录一个预先存在的问题

`dm-agent-trace view` 在 Windows GBK 控制台下读含中文的会话会
`UnicodeEncodeError`。已确认 `main` 分支同样失败，与本次改动无关；`PYTHONIOENCODING=utf-8`
下正常。留作独立问题。

## 怎么取回

全部实现都在本次重构的父提交里。要复活其中任何一个能力，**不要往内核里加**——
按 `docs/extensions.md` 写成外部扩展：`AgentCapability` 协议与六个生命周期钩子
都原样保留，Critic 就是 `before_finish`、熔断是 `before_tool_call` +
`after_tool_result`、Reflexion 是 `on_run_start` + `on_run_end`。

这正是扩展系统存在的意义：**内核不该为无法证伪的假设付出维护成本，而假设本身
不必因此消失。**

## 下一步

减法完成后，真正该投入的是让记分牌可用：把 coding + maintenance 合成一条命令出一个总分、
加 `compare` 子命令输出逐题 pass/fail 翻转与 token 成本对照、并把 13 题的噪声口径
（一题翻转 = ±7.7 个百分点）直接印在输出里。分数要能指导决策，才配叫记分牌。
