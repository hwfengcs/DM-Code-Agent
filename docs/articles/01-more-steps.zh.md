# 更多步数为什么未必让编程 Agent 更成功

[English](01-more-steps.en.md) · [文章目录](README.md) · [交互演示](https://hwfengcs.github.io/DM-Code-Agent/)

Agent 步数耗尽，最直接的干预是提高上限。在 DM-Code-Agent 的一次历史实验中，这让通过数从 22/30 变成 24/30，同时带来了 4 题回归和 30.6% 的估算 token 增长。

真正有用的发现，是弄清它把步数花在了哪里。

## 实验设置

2026 年 8 月 4 日，我们对同一组 30 道 coding 和 maintenance 任务各跑了一轮。两组使用 `deepseek-chat`、temperature 0、声明允许修改的文件，判分规则相同。唯一干预是把题目自带的 14–20 步上限统一改为 30。在当时的实现中，预算本身不进入模型 prompt。

| 指标 | 各题原始上限 | 统一上限 30 |
| --- | ---: | ---: |
| 通过任务 | 22/30 | 24/30 |
| 平均步数 | 11.7 | 14.2 |
| 估算 token | 1,458,155 | 1,903,954 |
| 步数耗尽 | 4 | 1 |
| trace 中识别的编辑自伤次数 | 13 | 25 |
| 出现编辑自伤的任务 | 6/30 | 9/30 |

共有 10 题翻转：6 题修好，4 题回归。总分只显示净增 2 题，掩盖了更大的行为变化。

这里的“编辑自伤”来自历史 trace 审阅：Agent 在步骤中承认自己刚才的编辑破坏或误删了代码。它是经审阅的过程指标，并非独立判分结果。token 是报告中的估算值，不是实际账单。

## 两种完全不同的耗尽

一类确实接近完成。`cross_file_user_contract` 的基线运行已经通过测试，最后几步还在核对文件内容。增加预算可能让这种运行走到完成动作。

另一类却是在修自己。`semver_compare` 的一次替换误删了 `core = parts[0]`，后续插入又放错了位置。额外步数在偿还编辑工具造成的损坏。

比较后续 trace，比只数耗尽次数更有信息量。原先耗尽的 4 题中，只有 `packaging_ci_contract` 真正使用了超出旧上限的步数：21 步，旧上限为 20，结果仍失败。另外 3 题分别在 9、13、16 步完成，比原上限还少。这些成功不能归因于新增加的步数。

这里还需要修正早期解释。最初日志把问题归因于过期行号，但[下一轮排查](../research-log/38-edit-file-precision.md)发现 read-before-edit 守卫已经会拦截过期读取。具体问题是：刚读完文件，模型仍可能选错区间；编辑回执又不展示修改后的代码，因而没有及时暴露误伤。

## 离线复核，不再调用模型

克隆并安装[项目](../../README_ZH.md)后，在仓库根目录执行：

```bash
python -m dm_agent.benchmarks.score_diff bench_reports/ablation-scope-20260804.json bench_reports/steps30-20260804.json
```

命令只读取两份已有报告，不发起模型请求。因为存在回归，**退出码 1 是预期结果**。这能复核聚合指标与逐题翻转，不会重新执行当年的 trace 人工审阅。

也可以直接复核通过数和 token 增幅：

```python
import json
from pathlib import Path

names = ["ablation-scope-20260804.json", "steps30-20260804.json"]
reports = [json.loads((Path("bench_reports") / name).read_text(encoding="utf-8"))
           for name in names]
for report in reports:
    summary = report["summary"]
    print(summary["variants"]["full"]["successes"],
          summary["total_estimated_tokens"])
before, after = [r["summary"]["total_estimated_tokens"] for r in reports]
print(f"Estimated token increase: {(after / before - 1) * 100:.1f}%")
```

应得到 `22 1458155`、`24 1903954` 和 `30.6%`。

## 能支持什么结论？

这次比较没有建立“增加预算让 Agent 变得更好”的证据，也不能证明更多步数总是有害。每个配置只跑了一轮，temperature 0 下模型输出仍有变化，总分同时掩盖了修复和回归。后来的重复实验进一步显示了逐题波动；历史日志里的经验噪声阈值不是统计显著性检验。

可以用于指导下一次工程修改的结论更具体：耗尽可能是预算不足，也可能是反复修复自身损坏。先检查最后的动作、确认新预算是否真的影响了完成边界，再把回归与总分一起看。在这个项目中，这些证据把下一步指向了[编辑接口](03-content-anchored-edits.zh.md)。

## 原始证据

- [实验与 trace 片段：devlog 37](../research-log/37-step-budget-and-edit-self-damage.md)
- [基线报告](../../bench_reports/ablation-scope-20260804.json)与 [30 步报告](../../bench_reports/steps30-20260804.json)
- [编辑机制的后续修正：devlog 38](../research-log/38-edit-file-precision.md)
- [重复实验与波动讨论：devlog 39](../research-log/39-observation-failure-classification.md)

[DM-Code-Agent](../../README_ZH.md)保留了这类排查所需的执行过程。可以先试[无需 key 的演示](../getting-started.md)，对比有测试证据和未验证就宣布完成的两次运行。
