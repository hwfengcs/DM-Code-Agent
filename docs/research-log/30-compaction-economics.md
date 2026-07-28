# 30 — 折叠经济性：净收益护栏与正收益粘性

## TL;DR

在 12 组脚本化长会话、396 次请求中共观察到 165 次折叠，其中 16 次让上下文反而
变大，负收益率为 **9.7%**。负收益都出现在早期只折叠少量消息时，单次额外增加
39–203 token（中位数 161）。

离线重放还显示：cadence 触发的折叠如果只在触发当步生效，后续请求会重新发送全量历史；
沿用最近一次折叠可显著节省 token，但不能盲目沿用负收益折叠。一个短会话中，首次折叠
多耗 197 token，盲目粘性又在后续三个请求各多耗 197 token，累计额外浪费 591 token。

因此本次同时落地两条规则：

1. 新折叠只有在 `estimated_tokens_after < estimated_tokens_before` 时才提交；
2. 只粘性复用最近一次已经证明为正收益的折叠，并把它写入 checkpoint 状态。

原始 `message` 条目仍然一条不删；被拒绝的候选不写空 `compaction` 条目，避免覆盖读侧正在
生效的上一份折叠。

## Context

会话树改造后，每次折叠都会留下 `compaction` 条目，暴露出两个既有问题：

- cadence 触发的折叠只影响当前请求，下一请求若未再次触发就回到全量历史；
- `<agent_memory>` 块有固定成本，折叠一两条短消息时可能比原文更大。

这两点都会改变真实发给模型的消息窗口，不能只靠确定性 eval 判断。项目的脚本化客户端
不读取请求消息，所以即使 eval 逐字段 `IDENTICAL`，也不能证明压缩行为安全。

## Method

临时脚本 `eval_reports/compaction_economics_probe.py` 生成 12 组完整 JSONL 会话：

- 6 组 cadence：`compress_every` 为 4 / 8 / 20；
- 6 组 token budget：预算为 60 / 120 / 300 / 600 / 1000；
- 历史长度为 12–48 轮，单条脚本化 observation 的主体为 24 / 96 / 512 字符；
- 全部使用本地 `ScriptedClient`，不需要 API key，也不调用托管模型。

每个 `llm_call` 都开启完整 I/O 捕获，再用 `rebuild_context` 计算三种窗口：

| 窗口 | 定义 |
| --- | --- |
| current | 当前实现真正发出的消息；未触发时回到全量历史 |
| sticky-all | 始终沿用最近一条 compaction，包括负收益折叠 |
| sticky-positive | 只沿用即时 token 收益严格为正的最近一条 compaction |

token 估算沿用项目规则 `ceil(content_chars / 4)`；system prompt 在三种窗口中完全相同，
因此统计时省略，不影响差值。脚本连续运行两次，输出 JSON 的 SHA256 完全一致。

## Results

### 折叠本身的净收益

| 触发方式 | 请求数 | 折叠数 | 负收益数 | 负收益率 | 拒绝负收益可直接节省 |
| --- | ---: | ---: | ---: | ---: | ---: |
| cadence | 202 | 19 | 4 | 21.1% | 702 token |
| token budget | 194 | 146 | 12 | 8.2% | 1,699 token |
| 合计 | 396 | 165 | 16 | 9.7% | 2,401 token |

16 次负收益折叠的扩张范围为 39–203 token，平均 150.1，中位数 161。它们全部发生在
历史刚越过 recent window、只折叠 1 / 3 / 5 条消息的阶段。

### 粘性的反事实估算

| 触发方式 | 当前请求 token | 当前相对全量节省 | sticky-all 额外节省 | sticky-positive 额外节省 |
| --- | ---: | ---: | ---: | ---: |
| cadence | 1,106,505 | 58,658 | 394,956 | 398,976 |
| token budget | 434,309 | 604,785 | 0 | 1,699 |
| 合计 | 1,540,814 | 663,443 | 394,956 | 400,675 |

cadence 场景下，sticky-positive 相对当前实现预计再节省 **36.1%** 请求 token；token-budget
本来几乎每个请求都会重新折叠，所以粘性本身没有额外收益，收益只来自拒绝负折叠。

`cadence4_short_tiny` 是不能单独落地 naive sticky 的反例：第 9 步只折叠 1 条消息，
窗口从 936 增至 1,133 token；如果继续沿用，该额外 197 token 会在第 10–12 步重复三次。

### 落地后的同场景复跑

实现护栏与正收益粘性后，用相同 12 组场景复跑：接受的 compaction 从 165 次降为 149 次，
负收益折叠从 16 次降为 0。实际请求 token 如下：

| 触发方式 | 改动前 | 改动后 | 实际减少 | 降幅 |
| --- | ---: | ---: | ---: | ---: |
| cadence | 1,106,505 | 710,729 | 395,776 | 35.8% |
| token budget | 434,309 | 432,572 | 1,737 | 0.4% |
| 合计 | 1,540,814 | 1,143,301 | 397,513 | 25.8% |

静态反事实原先估算总计减少 400,675 token，实际复跑减少 397,513，相差 3,162（0.8%）。
差值来自护栏回滚后未来 memory 内容与折叠时机发生变化，正好说明静态重放只能用来做决策，
最终仍必须跑实现后的真实消息窗口。

## Decision and implementation

实现采用“候选事务”而不是直接修改历史：

1. `ContextWindow` 在规划新折叠前保存 compressor 状态；
2. 候选严格降低 token 时才提交、记录 `compaction` 并更新最近有效折叠；
3. 候选无收益时恢复 memory、cadence 与摘要计数，不落空 compaction；
4. 没有新的正收益候选时，继续把最近有效折叠应用到当前完整历史；
5. `last_beneficial_compaction` 只保存逻辑历史下标与摘要，不保存任何 sink 的 entry id，
   并通过 compressor checkpoint 状态往返；老 checkpoint 缺少该字段时按 `None` 处理。

这保持了 append-only 不变式：原始消息既不覆盖也不删除；粘性只改变构造请求窗口的方式。

### 落地后的审计加固

实现后的独立审计又收紧了四个状态边界，但没有改变实验中的接受折叠或请求 token 总量：

- `on_run_end` 重试恢复 compressor 的完整进程内快照，包括自定义 memory 状态、cadence、
  摘要计数与 sticky 状态；checkpoint 序列化仍是另一份 JSON-safe 契约。
- 候选回滚不再 `deepcopy` 注入 memory 的 `__dict__`。memory 提供可覆盖的捕获/恢复钩子，
  锁、client 与共享 backend 的对象身份不会被复制或替换。
- 跨 run/resume 重新落 sticky 折叠时使用 `phase=sticky_reuse`、当前 before/after token 与
  当前 memory 数，不再伪装成旧 trigger 又触发了一次。
- `rebuild_context` 把每个 `run_start` 当作上下文硬边界，同时在 append-only session 中保留
  更早的全部条目供审计。

修复后用相同 12 个场景连续复跑两次；两份输出及此前的实装后报告 SHA256 均为
`b806758e32a35e2596432508bb1e6979032bc4d4cc18b87b2e3857264cb8804c`：仍是 149 次
接受折叠、0 次负收益折叠、请求 token 减少 397,513。

## Verification strength

本项验证强度刻意分成三层：

1. 单元/集成测试直接断言客户端实际收到的 messages，覆盖负收益拒绝、随后转正、跨请求
   粘性、checkpoint 恢复和老状态兼容；这是行为安全的主要证据。
2. 会话写入测试确认只有被接受的新折叠写 `compaction`，读侧继续用最新条目重建后续窗口。
3. 确定性 eval 仍需逐字段比较，但只能证明结果与 metadata 没有意外漂移，不能证明消息窗口。

离线 sticky-positive 是基于既有日志的反事实重放，没有模拟“拒绝候选后 memory 状态改变”
对未来摘要的全部影响。因此 36.1% 是方向性估算，不是线上模型成本承诺。

## Open questions / next bets

- 候选回滚能恢复本地状态，但启用 LLM 摘要时，已经发出的摘要请求无法撤销；后续可把候选
  构造改成真正的两阶段 memory clone，避免负候选产生一次无效模型调用。
- 当前粘性只复用最近一次正收益折叠。真实长会话中摘要相关性是否随任务阶段衰减，仍需带
  真实模型的质量评测；在此之前不增加自动失效策略。
- `memory_injection_count` 仍统计新折叠阶段，不把每次粘性复用当成一次新压缩；如果后续需要
  单独观测复用频率，应新增明确的 trace 指标，而不是改变旧字段含义。
