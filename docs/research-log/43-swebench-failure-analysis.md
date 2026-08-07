# 43 · 离线 SWE-bench 失败分析：三轴对齐而不混淆结论

- 日期：2026-08-07
- 前置工作：[42](42-swebench-crossrepo-50.md)
- 输入：已归档 prediction / 官方 report / selection manifest；本机可选 trace 与 harness detail
- 性质：离线分析工具，不改变 Agent、prediction 或官方判分

## TL;DR

真实 50 题运行已经有官方结果，但此前要手工把 prediction、Agent trace 与逐题 harness
detail 对齐。新增 `python -m swebench_verified.analyze` 后，这三类证据进入同一份确定性
JSON/Markdown 报告，同时仍保留三条互不替代的轴：

1. 官方 harness 结果：resolved / unresolved / empty patch / harness error；
2. harness detail：F2P 是否仍失败、是否同时出现 P2P 回归、patch 是否 apply；
3. Agent/trace 过程：主循环结束状态、步数、parse/guard、重复工具调用和验证缺口。

最重要的设计不是“多算一个分类”，而是拒绝把内部过程指标冒充外部正确性：
`dm_status=success` 不等于 resolved，max-steps 也不等于失败根因；一个实例可保留多个稳定
标签。缺失数据使用 `null` / `unmeasured` / `missing`，不再把“没有采到”写成真实 0。

本轮没有重新运行 Agent、Docker 或官方 verifier；只对既有归档和本机已有日志做离线读取。

## Context

[42](42-swebench-crossrepo-50.md) 归档了确定性跨仓库 20 → 50 结果。长期证据是三件套：

- [50 题 report](../../bench_reports/swebench-verified-crossrepo-50-20260806.json)
- [50 题 predictions](../../bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl)
- [50 题 selection manifest](../../bench_reports/swebench-verified-crossrepo-50-selection-20260806.json)

它们能回答“官方判了什么”“Agent 最终留下什么 patch”“样本边界是什么”，却不能自动回答：

- unresolved 是 F2P 没修完、P2P 回归，还是两者都有？
- 空 patch 之前有没有直接编辑、是否跑满步数、是否陷入重复调用？
- prediction 中的诊断字段缺失时，是真实 0 还是旧格式未测量？
- Agent 主循环主动结束和官方修复成功之间有多大错位？

手工统计的问题不只是慢。更危险的是口径会漂：一次把 `incomplete_ids` 的 450 个完整 split
未提交实例算进分母，另一次把 `dm_status=success` 当 resolved，再下一次把“调用过 edit”
写成“已证明发生有效修改”。分析器的目标是把这些边界固化成可测试契约。

## 三轴 taxonomy

### 1. 官方结果轴

唯一正确性来源仍是官方汇总 report：

- `resolved`
- `unresolved`
- `empty_patch`
- `harness_error`
- `incomplete`（本批 prediction 在有效 report 中没有结论）

核心 report 必须带 submitted/completed/resolved/unresolved/empty/error 的逐题 ID 数组；缺少
任一数组都直接报错，不能把损坏证据静默降级成全体 `unknown`。

分析器不重新实现 SWE verifier，也不读取测试输出猜 resolved。官方 report 的
`incomplete_ids` 被明确忽略：它对应完整 500 题 split 中未提交的实例，不是当前 manifest
的缺失集合。

### 2. Harness detail 轴

逐题 `report.json` 只读取布尔值与各测试集合的**数量**，不输出测试名称：

| 类别 | 含义 |
| --- | --- |
| `all_passed` | F2P 与 P2P 都没有失败；仍以官方汇总 report 的 resolved 为准 |
| `f2p_only` | 目标失败仍未清零，但没有观察到 P2P 回归 |
| `f2p_and_p2p` | 目标失败未清零，同时引入 P2P 回归 |
| `p2p_only` | F2P 已清零，但引入 P2P 回归 |
| `patch_apply_failure` | 官方 detail 明确记录 patch apply 失败 |
| `detail_unavailable` | 显式 detail 目录中没有该实例，或 empty patch 正常没有 detail |
| `unmeasured` | 调用者根本没有提供 detail 目录 |

`all_passed` 是必须补上的类别：若 detail 轴只列失败类型，21 个 resolved 实例会被错误地
塞进 unavailable，三轴分母就不再闭合。

### 3. Agent / trace 轴

prediction 的版本化 `dm_*` 字段优先；字段缺失时可从有效 trace 的 `run_end.metadata` 与事件
计数回填。保留 success / max-steps / exception、steps、duration、replans、parse
errors/repairs、truncations、edit guard/noop、repeat-search、edit-state revisit 与 edit-cycle
block。

trace 另外提供：

- `runtime.payload.instance_id` 的权威映射；文件名只作旧格式 fallback；
- append-only 文件出现多轮 `run_start` 时只选择最后一个完整 run，尾部不完整 run 明示 warning；
- direct write tool calls（`edit_file/create_file`）数量；
- mutation-capable calls（再包含 `run_shell/run_python`），用于保守判断 `no_edit` advisory；
- 由 action + 排序后的 `action_input` 构造的重复工具签名，不使用 Python `hash()`；
- 与现有 trace analyzer 一致的验证动作/完成前验证缺口口径。

重复工具签名与 SWE progress guard 的 repeat-search block 不是同一个指标：前者统计所有精确
重复调用，后者只统计被特定守卫拦截的重复搜索，不能相互替代。

## Missing、unmeasured 与真实 0

这次把“没数据”分成三种显式状态：

| 状态 | 语义 |
| --- | --- |
| `unmeasured` | 没有传 trace/detail；分析器从未检查该轴 |
| `missing` | 显式目录存在，但本批某实例没有对应文件 |
| `invalid` | 文件存在但局部 JSON/结构有问题；其余实例继续分析，该文件派生指标不进入 measured 聚合 |

旧 prediction 没有 `dm_diagnostics_version` 或某个新字段时，对应数值为 `null`。只有字段存在且
值为 0，或有效 trace 明确计数为 0，才叫真实零。每个聚合数值同时给出 `sum`、
`measured_count`、`unmeasured_count` 与总 `denominator`。

一条坏 trace 不应让整批失败，但核心边界必须 fail fast：prediction ID 不能重复，且顺序必须
逐项等于 manifest；官方 report 的核心 ID 数组必须齐全，四类结论必须互斥、并集完整、计数
一致。

这里有一个真实兼容点：官方 report 的 `submitted_ids` 会重排，归档 50 题 report 与 manifest
集合相同但顺序不同。因此 report ↔ manifest 校验是**集合相等**；只有 predictions ↔ manifest
才要求序列相等。若错误地对 report 做列表相等，已归档三件套本身就无法通过新工具。

## 多标签而不是单一根因

稳定标签顺序为：

```text
empty_patch, no_edit, max_steps, parse_error, guard_block,
f2p_unresolved, p2p_regression, harness_error, unknown
```

这些是可并存的观察信号，不是互斥根因。例如一个实例可以同时是 `max_steps + parse_error +
f2p_unresolved + p2p_regression`。单一分类会把重要信息覆盖掉。

`no_edit` 尤其保守：只有最终 patch 为空、trace 有效，且没有观察到 `edit_file/create_file`、
`run_shell/run_python` 中任何一个，才打这个 advisory。直接写工具调用过但最终 patch 为空，
只说明“过程里出现过直接写调用”；shell/Python 也可能改文件，因此不能据此证明有效修改或
宣称根因。

## 离线回归证据

对已跟踪的 50 题三件套运行分析器，得到与归档 report 一致的切片：

| 范围 | resolved | unresolved | empty patch | harness error |
| --- | ---: | ---: | ---: | ---: |
| 1–20 | 11 | 7 | 2 | 0 |
| 21–50 | 10 | 15 | 5 | 0 |
| 1–50 | 21 | 22 | 7 | 0 |

同一轮 predictions 的可加过程计数也闭合：non-empty 43、Agent success/max-steps 27/23、
steps 1757、parse errors 117、repeat-search blocks 49。这些数字来自已归档 prediction 与
[官方 report](../../bench_reports/swebench-verified-crossrepo-50-20260806.json)，不是新跑分。

本机已有的两个 trace 目录与 43 份逐题 detail 还做了额外离线核对：detail 分成
all-passed 21、F2P-only 10、F2P+P2P 9、P2P-only 3、patch apply failure 0；7 个空 patch
缺 detail，没有产生误报 warning。这些 ignored 本地日志没有被当成新的长期归档，也没有
重跑任何容器。

## 安全与可复现性

- 分析器只读取输入；`--json` / `--markdown` 与任何输入文件同路径时在写入前拒绝。
- trace 的题面、thought、action input、observation 与测试输出均不进入结果。
- harness detail 的 `FAIL_TO_PASS` / `PASS_TO_PASS` 只读取失败数量，不复制测试名称。
- failure 文本会遮盖环境 secret、Bearer、URL token 与常见 API key 前缀；坏 trace 不回填诊断。
- warning、标签、实例顺序、JSON 字段和 Markdown 表格均确定；不写时间戳，不用随机数。
- 25 个定向测试包含 CLI 离线性哨兵；本轮验证未联网、未启动 Docker、未调用 API，也未构造
  LLM client。

## Open questions / next bets

1. 用归档/可分享的数据生成稳定 failure matrix，并单独报告 unknown 覆盖率。
2. 先观察跨实例最稳定的标签组合，再决定是否提出一个小型、可证伪的结束守卫；分析器本身
   不应顺手改变 Agent 行为。
3. 若未来 selection manifest 增加逐题公开 repo/difficulty 元数据，应保持 v1 兼容，不能从
   当前 aggregate counts 反推单题属性。
4. 将重复工具签名与 repeat-search block 的差异用于定位“守卫没有覆盖的重复固定点”，但先做
   replay/synthetic 验证，不直接扩大 kernel。
