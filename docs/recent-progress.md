# 最近八轮进展（36–43）

这页把最近几轮从“修一个现象”串成可复核的证据链。每一轮都保留原始研究日志；这里只记录结论、边界和可复现的归档。

## 从过程护栏到真实外部验证

| 轮次 | 实验与结论 |
| --- | --- |
| [36](research-log/36-scope-constraint-ablation.md) | 明示任务的 `allowed_changed_files` 后，越界修改从 8 题降到 0。 |
| [37](research-log/37-step-budget-and-edit-self-damage.md) | 把上限盲目增加到 30 步成本更高，未观察到可归因收益；说明“多跑几步”不是稳定性策略。 |
| [38](research-log/38-edit-file-precision.md) | 内容锚定编辑后，编辑自伤从 13 次降到 0；47/47 次编辑都命中目标内容，编辑调用、总步数和 token 同步下降。 |
| [39](research-log/39-observation-failure-classification.md) | 来源分层消除了 34 次误报 replan；repeat-3 平均 pass rate 为 0.878，经验噪声底约 ±5 题（30 题约 ±16.7 个百分点）。 |
| [40](research-log/40-empty-patch-loops.md) | 对两个已知空 patch 题做定向复跑，空 patch 从 2 降到 0；但这不是 50 题总体空 patch 消失，打破循环也不等于修好题。 |
| [41](research-log/41-swebench-selection-manifest.md) | 建成完整 500 题候选集与确定性 selection manifest；20 题是 50 题的严格前缀，支持 resume 守卫和可审计复跑。 |
| [42](research-log/42-swebench-crossrepo-50.md) | 使用官方 SWE-bench 4.1.0 harness 跨 12 个仓库真实运行：20 题 11/20（55%），50 题 21/50（42%），最终 `error=0`。 |
| [43](research-log/43-swebench-failure-analysis.md) | 新增完全离线的三轴失败分析器，把官方结论、harness detail 与 Agent/trace 过程指标确定性对齐；没有重新运行模型、Docker 或 verifier。 |

## Verified 归档

这些是本轮长期证据（三件套：report、predictions、selection manifest）：

- [20 题 report](../bench_reports/swebench-verified-crossrepo-20-20260806.json) · [predictions](../bench_reports/swebench-verified-crossrepo-20-predictions-20260806.jsonl) · [selection](../bench_reports/swebench-verified-crossrepo-20-selection-20260806.json)
- [50 题 report](../bench_reports/swebench-verified-crossrepo-50-20260806.json) · [predictions](../bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl) · [selection](../bench_reports/swebench-verified-crossrepo-50-selection-20260806.json)

口径：这是本地确定性 50 题子集，不是完整 500 题分数，也不是 leaderboard 提交；50 题复用了前 20 题 predictions，只新增运行 30 题。50 题结果为 resolved 21、completed 43、empty patch 7、harness error 0。逐题 Docker 日志未纳入 Git，report/predictions/manifest 是可提交的长期证据。

Wilson 95% 区间：11/20 为 [34.2%, 74.2%]；21/50 为 [29.4%, 55.8%]；新增 21–50 的 10/30 为 [19.2%, 51.2%]。
