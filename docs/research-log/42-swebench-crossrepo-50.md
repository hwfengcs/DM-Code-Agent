# 42 · SWE-bench Verified 跨仓库 20 → 50 真实运行

- 日期：2026-08-06
- 前置工作：[41](41-swebench-selection-manifest.md)
- 模型：DeepSeek `deepseek-chat`，temperature 0

## TL;DR

确定性 selection manifest 首次进入真实运行。完整 Verified test split 有 500 题；20 题和
50 题样本均覆盖 12 个仓库，20 题严格等于 50 题的前缀。官方 SWE-bench 4.1.0 harness
最终给出：20 题 resolved **11/20 = 55%**，50 题 resolved **21/50 = 42%**，全部
`error=0`。新增的第 21–50 题单独看是 **10/30 = 33.3%**。

这不是两次独立复验：50 题复用了前 20 条 predictions，只新增运行 30 题。不能把
55% → 42%解释成一次独立实验的 13 个百分点回归；更直接的结论是后 30 题包含更高比例
的 `1-4 hours` / `>4 hours` 难题，暴露了更明显的长探索、空 patch 和未完成修复。

## 实验契约

| 项目 | 20 题 | 50 题 |
| --- | --- | --- |
| candidate fingerprint | `13b4d320ef91ad2bca8772e1035d568df6f111b4acb795c9f617afae0f5f7a3f` | 同左 |
| selection signature | `13f72bbd078b868f65185254aec038a4ec8028909060e12872ce5dcea56d483b` | `86d5f44e939f69e92292c23cba844e862985b2e9dd574d19067d02d8fdb9f508` |
| repo 数 | 12 | 12 |
| difficulty | easy 11 / medium 9 | easy 21 / medium 18 / hard 8 / very hard 3 |
| prefix check | — | manifest IDs 与 prediction 前 20 条均逐条一致 |

运行参数：`--max-steps 60 --timeout 180`；官方判分使用 `--max-workers 4
--timeout 1800`。预测开始时 HEAD 为 `16fd255`，并带有本轮真实 Windows 运行暴露出的
workspace tar/symlink 工作树修复；最终判分前又补上了 harness UTF-8 修复。归档提交包含
这些修复及完整测试，不能把裸 `16fd255` 单独当成可复现实验源码身份。

## 官方结果

| 范围 | submitted | completed | resolved | unresolved | empty patch | error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 前缀 1–20 | 20 | 18 | **11 (55.0%)** | 7 | 2 | 0 |
| 新增 21–50 | 30 | 25 | **10 (33.3%)** | 15 | 5 | 0 |
| 总体 1–50 | 50 | 43 | **21 (42.0%)** | 22 | 7 | 0 |

新增 30 题的 15 个非空 unresolved 可进一步分成：6 题 F2P 未修完但没有 P2P 回归，
6 题 F2P 未修完且同时有 P2P 回归，3 题已经通过全部 F2P、却引入 P2P 回归。后者说明
“修到目标测试通过”仍不等于维护任务完成，原行为保护必须进入 Agent 的结束判定。

难度分层只作描述，不声称统计显著：前 20 的 `<15 min fix` 为 9/11，新增 30 题为
6/10；新增的 `15 min - 1 hour` 为 3/9，`1-4 hours` 为 1/8，`>4 hours` 为 0/3。

## Agent 过程指标

| 范围 | non-empty | success / max-steps | steps | 时长总计 | 时长中位数 | parse errors | repeat-search blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1–20 | 18 | 13 / 7 | 570 | 2782.91 s | 51.64 s | 38 | 10 |
| 21–50 | 25 | 14 / 16 | 1187 | 9971.39 s | 196.20 s | 79 | 39 |
| 1–50 | 43 | 27 / 23 | 1757 | 12754.30 s | 187.34 s | 117 | 49 |

总体另有 parse repairs 327、truncations 44、edit guard blocks 2、identity no-op 8、
edit-state revisit 1、edit-cycle block 0。`dm_status=success` 只表示 Agent 主循环主动结束，
不能代替官方 resolved；反过来，max-steps 也可能留下可判分 patch。

## 真实运行修掉的 host 故障

1. Django 镜像含 symlink，Windows `docker cp` 会因创建链接权限失败。预测端改为读取
   `docker cp ...:/testbed/. -` 的 tar；Windows 按 Git `core.symlinks=false` 写 link
   target 文本，非 Windows 保留原生 symlink 和 mode。安全解包拒绝路径穿越、重复目标、
   Windows 保留名和大小写冲突。真实 Django 探针的 `git status --porcelain` 为 0 行。
2. 官方 harness 在中文 Windows 上用默认 GBK 写测试输出，遇到 `ë`、孟加拉数字等字符会在
   测试完成后抛 `UnicodeEncodeError`。判分入口现在显式统一 UTF-8，并继续强制 shell
   脚本 LF。20 题前三份受编码故障影响的报告不进入最终数字；可信报告为 error=0 版本。
3. 50 题首次判分在生成 test specs 时遇到 GitHub Raw 瞬时 SSL EOF，尚未进入逐题测试。
   原参数重试后 43 个非空 patch 全部完成，error=0；该网络故障不计入能力失败。
4. 单题镜像首次下载可持续数十分钟。现在单次 `docker pull` 有 1 小时上限，并保留三次
   可复用已下载 layer 的重试，防止永久挂起。

## 归档与成本边界

归档三件套：

- `bench_reports/swebench-verified-crossrepo-{20,50}-20260806.json`
- `bench_reports/swebench-verified-crossrepo-{20,50}-predictions-20260806.jsonl`
- `bench_reports/swebench-verified-crossrepo-{20,50}-selection-20260806.json`

本轮实际发生 HuggingFace/GitHub 网络请求、Docker 镜像下载和 DeepSeek API 调用。最终
Docker 本地镜像超过 90 GB。predictions 没有记录供应商账单 token 或精确费用，因此这里
不估算并冒充真实 API 金额；精确成本只能以供应商账单为准。

## 下一步

- 从 30 题新增 tranche 里选固定 sentinel 做 repeat 3，而不是重跑全部 50 题。
- 优先研究 P2P 回归结束门禁、空 patch 长循环，以及 117 次 parse error 的集中来源。
- 增加离线 SWE failure analyzer，把 prediction/trace/官方 report 自动合并，避免手写统计。
