# 35 · Claude Code (Opus 5) vs DeepSeek + dm-agent：同题对局

- 日期：2026-08-03
- 相关：[33](33-scope-reduction.md) [34](34-benchmark-expansion.md)
- 原始数据：`bench_reports/arena-claude-opus5-20260803.json`（Claude）、
  `bench_reports/baseline-20260803.json`（DeepSeek）

## TL;DR

在完全相同的 13 道题、完全相同的判分逻辑下：

| | pass_rate | 说明 |
| --- | --- | --- |
| Claude Code + Opus 5 | **7/13 = 0.538** | 通过 Claude Code 的 sub-agent 跑 |
| DeepSeek + dm-agent | **5/13 = 0.385** | `dm-agent-bench --suite all` |

**差距只有 2 题**，在 13 题规模下（一题 = 7.7 点）够不上显著，而且不是单向碾压——
Claude 赢 3 题、输 1 题。

真正的发现在另一处：Claude 跑全 30 题时 **隐藏测试通过 28/30（93.3%），
最终只有 19/30（63.3%）算过**。11 个失败里 **10 个是「改了不该改的文件」**。
换用更强的模型没有消除这个失败模式，反而让它占比更高——因为「写不出代码」的
失败全消失了，剩下的全是纪律问题。

## 实验设计与公平性控制

对比 agent 很容易做成不可信的实验。这次显式控制了四点：

1. **判分逻辑必须是同一套。** 判分脚本直接 import `dm_agent.benchmarks.runner`
   的 `_score_run` / `_snapshot_workspace` / `_diff_workspace`，而不是另写一套。
   否则比较的不是同一件事。
2. **信息量必须等同。** 每个工作区只放 `setup_files` 加一份 `TASK.txt`，内容是
   `task.prompt` 逐字原文。**特意不放 `allowed_changed_files`**——dm-agent 的 prompt
   里没有它，sub-agent 看到就是不公平优势。含该字段的 `meta.json` 在实验前移出了
   竞技场目录。
3. **隐藏测试绝不落地。** 建工作区后校验 `rglob("*hidden*")` 为空，判分前再校验一次。
4. **执行者必须没有本会话的上下文。** 这一点最初被我判断错了：我以为「我写了其中
   17 道题的隐藏测试，所以不能跑那 17 题」。实际上 sub-agent 是独立 context，
   看不到主对话的任何内容。直接对比仍然只用原 13 题——那也是唯一有 DeepSeek 对照
   数据的子集。

**无法消除的三条不对称**，写在这里而不是藏起来：

- dm-agent 有 12–20 步的硬步数预算，sub-agent 没有等价约束。
- 工具集不同：dm-agent 用自己的 17 个内置工具，sub-agent 用 Claude Code 的工具。
- 17 道新题由我设计。设计时按「考察什么能力」而非「Claude 好不好做」，且每题都写过
  参考解验证可解——但这仍是一种间接偏向。直接对比只用原 13 题正是为了避开它。

## 一个把整轮实验作废的判分错误

第一轮判分结果是 **0/30**。那不是 Claude 的表现，是我的 bug：

```python
# 错的
prepare_workspace(task, workspace, include_hidden=True)
# 对的（dm-agent 自己在 runner.py:691 就是这么做的）
_write_files(workspace, task.hidden_files)
```

`prepare_workspace` 会**先重写 `setup_files`**，等于把每个工作区的实现恢复成初始的
有 bug 版本，然后才加隐藏测试。于是隐藏测试跑的是原始代码，必然全挂。

代价是 30 个 sub-agent 的成果被覆盖且不可恢复（transcript 文件为 0 字节，
`__pycache__` 的 .pyc 反编译不可信），全部重跑。

**教训写成了脚本里的注释**，并且修好后先做了一件本该一开始就做的事：
**用 17 份已验证的参考解回测判分器**，17/17 判为 PASS 才敢再用。
一个判分器在拿它测别人之前，应该先证明它认得出正确答案。

## 结果

### 同题对局（原 13 题）

| 任务 | Claude | DeepSeek |
| --- | --- | --- |
| slugify_cleanup | PASS | PASS |
| order_total_edges | PASS | PASS |
| ttl_cache_lru | **PASS** | FAIL |
| normalize_users | PASS | PASS |
| stats_summary | PASS | PASS |
| inventory_reservations | **PASS** | FAIL |
| config_precedence | FAIL | FAIL |
| patch_summary_name_status | FAIL | FAIL |
| retry_regression_tests | FAIL | **PASS** |
| safe_workspace_join | FAIL | FAIL |
| cross_file_user_contract | FAIL | FAIL |
| cli_config_docs_contract | **PASS** | FAIL |
| packaging_ci_contract | FAIL | FAIL |
| **合计** | **7/13** | **5/13** |

注意最后五行：两边**在同样的题上一起失败**。这些题的共同点是多文件 + 有
`allowed_changed_files` 约束。

### Claude 全 30 题

```
coding        15/15  ← 满分，对 Opus 5 已无区分度
maintenance    4/15
总计          19/30 = 0.633
隐藏测试      28/30 = 0.933
```

失败归类：

| 原因 | 题数 | 明细 |
| --- | --- | --- |
| 改了不该改的文件 | **10** | 9 题改 `tests/test_public_*.py`，1 题新建 `conftest.py` |
| 隐藏测试没过 | 1 | `packaging_ci_contract` |

`safe_workspace_join` 是最典型的一例：sub-agent 找出了两个真实安全漏洞
（sibling-prefix 前缀绕过、绝对路径被静默吞掉而非拒绝），修得漂亮，还用目录 junction
验证了符号链接逃逸——然后因为顺手把回归测试补进了不该动的文件，判 0 分。

## 结论

1. **benchmark 有区分度，而且区分的不是模型强弱。** 两个能力差距明显的 agent 只差
   2 题，因为瓶颈不在模型。这比「强模型赢麻了」有用得多——后者说明题目在测模型，
   前者说明题目在测 agent 系统。
2. **coding suite 对前沿模型已经饱和**（15/15）。后续加题应全部投向 maintenance：
   多文件、跨文件契约、带改动范围约束的任务。
3. **最高杠杆的改进不是换模型，是加一条约束守卫。** 在 `before_tool_call` 上拦下对
   `tests/` 的写入，理论上能让 Claude 从 19/30 到 29/30、DeepSeek 从 5/13 到 8/13。
   这正是扩展系统的典型用法，不需要碰内核——也正好可以用 `dm-agent-score-diff`
   量化它到底值多少分。
4. **"隐藏测试通过率"与"pass_rate"的落差是这个 benchmark 最有信息量的指标**，
   比任何一个单独的分数都有用。它把「不会写代码」和「不守规矩」分开了。

## 补测：DeepSeek 的 30 题数据（2026-08-04）

| 指标 | DeepSeek + dm-agent | Claude Code + Opus 5 |
| --- | --- | --- |
| pass_rate | **15/30 = 0.500** | **19/30 = 0.633** |
| hidden_test_pass_rate | 27/30 = 0.900 | 28/30 = 0.933 |
| coding (15) | 12/15 | 15/15 |
| maintenance (15) | 3/15 | 4/15 |
| 成本 | 15.4 分钟 / 1,543,977 tokens | — |

差 4 题 = 13.3 点。30 题下一题 3.3 点，刚够得上"不是噪音"，但不是代差。

**全部差距来自"跑不完"，不是"写不对"**：

| 失败原因 | DeepSeek | Claude |
| --- | --- | --- |
| 改了不该改的文件 | 8 题 | 10 题 |
| 其他（多为 Max steps exceeded） | 7 题 | 1 题 |

两边违规题数几乎相同（8 vs 10），差距全在第二行。Claude 赢下的
`slugify_cleanup` / `normalize_users` / `cli_config_docs_contract` 三题，DeepSeek 全是
步数耗尽——而 `slugify_cleanup` 是全套最简单的题之一（Claude 8 步做完）。
**这是模型效率问题，不是 dm-agent 的架构问题。**

**10 道题两边一起挂**（占全套三分之一）：config_precedence、
patch_summary_name_status、safe_workspace_join、cross_file_user_contract、
packaging_ci_contract、billing_period_boundary、sql_where_builder、
idempotent_job_runner、filename_sanitizer、log_redaction。
共同点：全部带 `allowed_changed_files` 约束，且两边都是代码写对了、去补测试被判违规。

### 天花板测算

`hidden_test_pass_rate = 0.900` 就是 DeepSeek + dm-agent 的能力上限，现在只兑现了
0.500。中间 40 个百分点全是过程纪律损耗：

| 阶段 | 预期 pass_rate |
| --- | --- |
| 现在 | 0.500 (15/30) |
| 修好「改测试」后 | **~0.767 (23/30)** — 那 8 题的隐藏测试本来就过 |
| 再解决步数耗尽 | ~0.90 (27/30) |

修好第一条就能超过 Claude Code 当前的 19/30，且不需要换模型。

## Open questions / next bets

1. DeepSeek 的 30 题数据还没跑，目前只能在 13 题上直接对比。补齐后可以看
   maintenance 新增 8 题是否同样区分不出两者。
2. 步数预算的不对称能否消除？给 sub-agent 加一个显式的工具调用次数上限或许可行，
   但那与 ReAct 的「步」仍不是同一个单位。
3. 「改了不该改的文件」在两个模型上都是首要失败模式。值得单独做一个消融：
   把 `allowed_changed_files` 明确写进 prompt，看失败率降多少——如果降到接近零，
   说明这是提示问题；如果不降，说明是 agent 的自控问题，那才需要守卫。
