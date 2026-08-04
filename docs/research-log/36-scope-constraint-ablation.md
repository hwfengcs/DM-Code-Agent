# 36 · 改动范围约束消融：agent 不守的规矩，它从来没被告知

- 日期：2026-08-04
- 相关：[34](34-benchmark-expansion.md) [35](35-agent-arena-claude-vs-deepseek.md)
- 原始数据：`bench_reports/baseline-30task-20260804.json`（对照组）、
  `bench_reports/ablation-scope-20260804.json`（实验组）

## TL;DR

把 `allowed_changed_files` 写进 prompt，**「改了不该改的文件」从 8 题降到 0 题**，
pass_rate `0.500 → 0.733`（+23.3 点）。

这是**提示问题，不是自控问题**。devlog 35 里那条「最高杠杆的改进是加一条约束守卫」
的推断被证伪了——守卫不用写，因为根本不需要拦：agent 一旦知道边界在哪就不越界。

最有说服力的不是总分，是**「隐藏测试通过率 − pass_rate」这个落差从 40 个百分点
塌到 10 个**。它衡量的正是「代码写对了却没算过」的纯过程损耗。

代价栏也得看：`hidden_test_pass_rate` 反而从 0.900 掉到 0.833，且 coding 那 15 道
prompt 逐字未变的题里有 3 题在翻转——噪声底比想象的高，见「诚实栏」。

## Context

[devlog 35](35-agent-arena-claude-vs-deepseek.md) 留下一个刺眼的落差：DeepSeek + dm-agent
在 30 题上 **隐藏测试过 27/30 = 0.900，最终只算 15/30 = 0.500**。中间 40 个百分点
不是「写不出代码」，是「过程纪律」。拆开 15 道失败题：

| 失败原因 | 题数 |
| --- | --- |
| 改了不该改的文件 | 8 |
| 其他（多为 Max steps exceeded） | 7 |

动手前先把这 8 题的原始记录逐条核对了一遍，两个事实让假设变得可证伪：

1. **8 题违规的文件 100% 是 `tests/test_public_*.py`。** 没有一题是改错了实现文件、
   或者顺手动了无关模块。失败模式高度集中，不是随机越界。
2. **8/8 违规题的 `hidden_test.returncode == 0`。** 代码全部写对了，纯粹被判分规则挡下。

于是「修好这一条 → 23/30 = 0.767」不是乐观估计，是精确算术：那 8 题的隐藏测试
本来就是绿的，只要不越界就直接转 PASS。

### 根因：这既是 agent 的失败，也是 benchmark 的设计缺陷

`dm_agent/benchmarks/tasks.py` 里 `MAINTENANCE_PROMPT_SUFFIX` 对全部 15 道
maintenance 题拼上同一段话，其中一句是：

> "...update tests when the task asks for a regression test..."

而 `allowed_changed_files` **从来没有出现在交给 agent 的 prompt 里**——
devlog 35 甚至专门把含该字段的 `meta.json` 移出竞技场目录，以免 sub-agent
拿到 dm-agent 没有的信息。公平是做到了，但代价是：

**agent 被一句 prompt 鼓励去动测试，然后按一条它看不见的规则判 0 分。**

在这种设定下测出来的「不守规矩」，测的到底是 agent 的自控力，还是我们没说清楚？
这个问题不回答，任何守卫机制的收益都无法归因。

## 实验设计

一个变量：**把每题的 `allowed_changed_files` 写进交给 agent 的 prompt**。
其余一切不变——同一模型、同一温度、同一步数预算、同一判分逻辑、同一任务集。

### 关键约束：不能改 `task.prompt` 字面量

`benchmark_task_fingerprint()` 把 `task.prompt` 算进指纹，指纹又进 `suite_signature`。
直接改 prompt 字符串会有两个后果：

- CI 的 manifest guard fail（可以重新生成 baseline，是小事）
- **`dm-agent-score-diff` 按设计拒绝跨任务集比较并 exit 2**（这是大事）

对照组数据是 15.4 分钟 / 154 万 token 换来的，不能重跑。所以约束声明做成
**runner 侧的运行时开关**：`task.prompt` 逐字不动，只在调 `agent.run()` 前拼接
派生视图 `BenchmarkTask.scoped_prompt()`。

```python
prompt = task.scoped_prompt() if config.declare_allowed_files else task.prompt
```

指纹不变 → `suite_signature` 不变 → 两份报告直接可比。这条不变量由
`tests/test_coding_benchmarks.py::test_declaring_allowed_files_does_not_change_the_suite_signature`
守着，谁把约束搬进 `task.prompt` 都会立刻红。

实测两条 manifest guard 都返回 `compatible`，signature 逐字一致
（coding `c846387398b2ab63`、maintenance `1a633dda3e5bda09`）。

### 措辞的三个决定

约束段追加在 `MAINTENANCE_PROMPT_SUFFIX` **之后**——后者那句 "update tests..."
是已知的反向诱导，靠末尾位置压过它。内容上三处是照着实际失败样本写的：

- **「即使实现完全正确也判失败」**——对齐 `_score_run` 的真实行为。8 道违规题的
  隐藏测试全是绿的，不写这句，agent 有理由认为「测试都过了应该没事」。
- **「包括新建文件」**——devlog 35 里 Claude 有一题栽在新建 `conftest.py`。
- **「读不受限，只限写」**——否则约束会误伤探索步骤，把违规换成步数耗尽。

**逐题列出实际允许的文件，不能简化成「不要改测试」**：有 4 道题
（`retry_regression_tests`、`sort_stability_regression`、`cli_config_docs_contract`、
`packaging_ci_contract`）的可改范围里本来就含 `tests/`，一刀切会把它们判错。
前两题在对照组里是 PASS——说明当边界清楚时 agent 表现正常，这本身就是假设的旁证。

### 为什么跑全 30 题而不是只跑 maintenance 15 题

coding 15 题**全部没有** `allowed_changed_files`，`scoped_prompt()` 对它们是逐字
no-op（有单测守着）。多跑这 15 题花掉一半 token，换来两样东西：

- `score-diff` 要求同一任务集才肯比 pass_rate；
- **coding 那半边的翻转数就是免费的噪声底估计**。temperature=0 不等于确定性，
  prompt 逐字相同的题目若也在翻转，maintenance 的小幅改善就不构成证据。

### 复现

```bash
python -m dm_agent.benchmarks.cli --suite all --declare-allowed-files \
  --trace-dir bench_reports/ablation-scope-traces \
  --output bench_reports/ablation-scope-20260804.json \
  --markdown bench_reports/ablation-scope-20260804.md

python -m dm_agent.benchmarks.score_diff \
  bench_reports/baseline-30task-20260804.json \
  bench_reports/ablation-scope-20260804.json
```

对照组即 devlog 35 的 `baseline-30task-20260804.json`，同命令去掉
`--declare-allowed-files`。报告顶层的 `prompt_policy.declare_allowed_files`
标明自己是哪一组。

## 结果

DeepSeek `deepseek-chat`，temperature 0，variant `full`，30 题各跑一次。

| 指标 | 对照组（不声明） | 实验组（声明） | 差 |
| --- | ---: | ---: | ---: |
| **pass_rate** | 0.500 (15/30) | **0.733 (22/30)** | **+23.3 pts** |
| hidden_test_pass_rate | 0.900 (27/30) | 0.833 (25/30) | −6.7 pts |
| agent_completion_rate | 0.800 | 0.833 | +3.3 pts |
| **hidden − pass 落差** | **0.400** | **0.100** | **−30 pts** |
| coding | 12/15 | 13/15 | +1 |
| maintenance | 3/15 | 9/15 | **+6** |
| tokens | 1,543,977 | 1,458,155 | −5.6% |
| 平均步数 | 11.8 | 11.7 | −0.1 |

失败模式的变化才是主结果：

| 失败原因 | 对照组 | 实验组 |
| --- | ---: | ---: |
| **改了不该改的文件** | **8** | **0** |
| 步数耗尽 | 6 | 4 |
| 隐藏测试没过 | 1 | 4 |

`dm-agent-score-diff` 判定 9 题翻转（8 fix / 1 regression），且因为 `suite_signature`
两侧一致（`cd8c03782d763ccc`），它肯直接比 pass_rate 而不是 exit 2 ——
运行时开关的设计红利在这里兑现。

### 8 道违规题的去向

一题不剩地不再违规，但没有全部转成 PASS：

| 任务 | 对照组 | 实验组 |
| --- | --- | --- |
| `billing_period_boundary` | 违规 | **PASS** |
| `error_propagation_contract` | 违规 | **PASS** |
| `filename_sanitizer` | 违规 | **PASS** |
| `safe_workspace_join` | 违规 | **PASS** |
| `sql_where_builder` | 违规 | **PASS** |
| `cross_file_user_contract` | 违规 | 步数耗尽（隐藏测试**已通过**） |
| `config_precedence` | 违规 | 隐藏测试没过 |
| `log_redaction` | 违规 | 隐藏测试没过 |

另有 3 题原本步数耗尽的转成了 PASS（`slugify_cleanup`、`normalize_users`、
`idempotent_job_runner`），1 题原本 PASS 的退成步数耗尽（`semver_compare`）。

### 新的瓶颈：4 题步数耗尽，其中 3 题代码已经写对

实验组剩下的 8 道失败题：

| 任务 | 套件 | 原因 | 隐藏测试 |
| --- | --- | --- | ---: |
| `semver_compare` | coding | 步数耗尽 | **通过** |
| `cross_file_user_contract` | maintenance | 步数耗尽 | **通过** |
| `cli_config_docs_contract` | maintenance | 步数耗尽 | **通过** |
| `packaging_ci_contract` | maintenance | 步数耗尽 | 不通过 |
| `ttl_cache_lru` | coding | 隐藏测试没过 | — |
| `config_precedence` | maintenance | 隐藏测试没过 | — |
| `patch_summary_name_status` | maintenance | 隐藏测试没过 | — |
| `log_redaction` | maintenance | 隐藏测试没过 | — |

**违规那一栏空了，首要失败模式换成了步数耗尽**，且其中 3 题的隐藏测试已经是绿的
——代码写完了，只是没在预算内走到 `finish`。这正是 devlog 35 说的「DeepSeek 更啰嗦」
那个问题，现在它从第二顺位升到了第一顺位。

## 诚实栏：三件对结论不利的事

**1. 噪声底比想象的高。** coding 那 15 题的 prompt 逐字未变（`scoped_prompt()` 对
无约束任务是 no-op，有单测守着），却有 **3 题翻转**：

| 任务 | 变化 | 隐藏测试 |
| --- | --- | ---: |
| `slugify_cleanup` | FAIL → PASS | 通过 |
| `normalize_users` | FAIL → PASS | 通过 |
| `semver_compare` | PASS → FAIL | 通过 |

净 +1 题，但抖动幅度是 ±3 题 = ±10 个百分点，比 devlog 34 按题数算出的 ±3.3
（一题的名义权重）大得多。三题全部 `hidden_ok=True`——翻转的不是代码质量，
是能不能在 12–20 步里收尾。**所以 maintenance 的 +6 题才算证据，+1 题的差异不算。**

**2. `hidden_test_pass_rate` 掉了。** 27/30 → 25/30，正好是
`config_precedence` 和 `log_redaction` 这两题：对照组里它们改了可见测试**并且**
代码写对了，实验组里它们守住了范围**但代码写错了**。两种解释都还站得住：

- 之前是靠改可见测试来试探需求，剥夺这个手段后推断能力下降；
- 或者纯属运行间随机（`log_redaction` 两组都是 8 步就自认为做完）。

单跑一轮分不出来。要分辨得上 `--repeat`，那是另一笔预算。**这个数字不该被
「+23.3 点」盖过去。**

**3. 这不是同一个测试。** 声明约束之后，benchmark 测的东西变了：

- 关闭 = 「agent 能否推断出没写出来的项目规范」——更接近真实世界的模糊需求；
- 开启 = 「agent 能否遵守明确给定的约束」——隔离出纯执行能力。

后者分更高不代表 agent 变强了。所以开关**默认保持关闭**，两组数据都存档，
换记分口径是一个需要显式做的决定，不是一次悄悄的提分。

## 结论

1. **devlog 35 的推断被证伪。** 那里写着「最高杠杆的改进不是换模型，是加一条约束
   守卫……理论上能让 DeepSeek 从 5/13 到 8/13」。守卫不用写了——违规归零靠的是
   把规则说出来。**先花 15 分钟做消融，省下一个不需要存在的扩展。**
2. **「隐藏测试通过率 − pass_rate」是这套 benchmark 最有信息量的指标**（devlog 35
   第 4 条结论），这次它给出了可执行的读数：落差 0.400 说明有 40 点卡在过程上，
   补一句 prompt 就收回 30 点。剩下的 0.100 才是真正需要动系统的部分。
3. **判分规则必须对被判者可见。** 「按一条 agent 看不见的规则判 0 分」测出来的
   不是自控力，是我们没说清楚。这是 benchmark 的设计缺陷，不是 agent 的失败模式。
4. **下一个瓶颈是步数耗尽**，且 4 题里有 3 题的隐藏测试已经通过——离终点只差收尾。

## Open questions / next bets

1. **步数耗尽现在是首要失败模式**（4 题，3 题代码已写对）。值得先量的是
   「加大 `max_steps` 能买回几题」——那是纯预算问题，跑一轮就知道，
   而且能把「模型啰嗦」和「agent 不会收尾」分开。
2. **`hidden_test_pass_rate` 的 −6.7 点需要 `--repeat 3` 才能定性**：是剥夺了
   试探手段，还是运行噪声。两题的样本量说明不了任何事。
3. **要不要换记分口径？** 声明约束更公平，但会让 `baseline-30task-20260804.json`
   与 `arena-claude-opus5-20260803.json` 这两份历史数据不可比。建议保持默认关闭，
   把实验组作为并列的第二条记分线。
4. **同样的消融该在 Claude 那一侧做一遍**：devlog 35 里 Claude 有 10 题违规，
   其中 9 题是改 `tests/test_public_*.py`。如果它也归零，就说明这个失败模式
   与模型强弱无关，是所有 agent 系统共有的信息缺失问题。

