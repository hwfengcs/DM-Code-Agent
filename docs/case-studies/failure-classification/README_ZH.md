# 12 项针对性检查通过了，修复仍然不能交付

[English](README.md) · [在线运行报告](https://hwfengcs.github.io/DM-Code-Agent/cases/failure-classification.html) · [下载 HTML](report.html) · [证据清单](evidence.json)

2026-11-14，我们让 DM-Code-Agent 在自己的历史仓库副本中修复一个真实缺陷。
12 项给定回归检查全部通过后，更大范围的测试仍有 2 项失败；Agent 继续排查，最终耗尽 14 步预算。
这是一次保留下来的**未完成修复**，补丁没有合入当前 Agent。

## 真实问题与实验设置

历史提交 [`bd35d253`](https://github.com/hwfengcs/DM-Code-Agent/tree/bd35d253abb18cabdaedf1caa1d5dd91cd985f59)
会扫描工具观察全文中的 `error` 等标记。读取正常源码 `from errors import NotFound`
也可能被判成失败；反过来，退出码 2 等真实失败又可能漏判。

这个问题后来在 [`8025044`](https://github.com/hwfengcs/DM-Code-Agent/commit/8025044dd0b75f819e81ecb6d23e42a6b35d9a5b)
中修复。本次真实模型运行从其父提交开始，只提供[任务](task.txt)和[12 项检查](regression_test.py.txt)，
未提供历史解法。执行任务的是当前 v2.1.0 Agent（`c07646a`）。

| 检查 | 修改前 | 修改后 |
| --- | --- | --- |
| 给定回归检查 | 5 通过、7 失败 | 12 通过 |
| 历史完整测试集，加给定检查 | 459 通过、7 失败 | 464 通过、2 失败 |
| Agent 结束状态 | 14 步上限 | `max_steps_exceeded` |

第 1、11 步运行针对性检查，第 12 步运行更大范围测试。剩余失败都在 `tests/test_evals.py`：
新的失败分类行为与旧 eval fixture 不匹配。历史正式修复也调整了 fixture 内容；
而本次任务明确只允许修改分类器和 Agent 调用点。因此不能把 12 项通过写成完整修复成功。

另一个新建工作区只应用归档补丁、没有调用模型，复现了相同结果：
[修改前](before.txt)、[修改后](after.txt)、[完整测试前](before-full-suite.txt)、[完整测试后](after-full-suite.txt)。
这些是历史副本的结果，不是当前主分支的测试失败。

## 成本与人工参与

- 配置为 DeepSeek / `deepseek-chat`，服务响应报告的模型为 `deepseek-flash`。
- 只运行一次真实尝试：14 步、17 次完成的客户端请求，包含规划和重规划；未单独统计传输重试次数。
  本次配置开启规划、关闭压缩，最多重规划 2 次，只提供 5 个文件/测试工具，每次请求最多输出
  2,400 tokens；完整配置见[证据清单](evidence.json)。
- 服务累计报告输入 164,476 tokens、输出 4,670 tokens，共 169,146；输入中包含
  145,024 个缓存命中 tokens。[逐请求用量](requests.json)已归档，没有查询账单或推算金额。
- 人工提供任务和回归检查，运行期间未手工修改工作区。模型只改了
  `dm_agent/core/observation.py` 和 `dm_agent/core/agent.py`，给定测试字节完全未变。
- 没有新增 SWE-bench 运行或总体 benchmark 分数。单个选定历史任务不能代表通用修复成功率。

## 无模型 key 复现

使用完整 Git clone，安装 Python 3.10+ 开发依赖后执行：

```bash
uv sync --frozen --extra dev
uv run --frozen python scripts/reproduce_maintenance_case.py --output build/case-reproduction --full-suite
```

浅克隆需要先用 `git fetch --unshallow` 取得历史。脚本创建新 detached worktree，添加给定检查，
运行测试，应用[归档补丁](agent.patch)，再运行测试；`--full-suite` 额外运行修改前后的历史完整测试集。
全程零模型请求，不改当前 checkout，保留原工作区和输出。重复执行时使用新目录。

脚本退出码只表示是否成功复现针对性检查结果；更大范围测试的独立退出码保存在 JSON 中。
复现成功不等于补丁可合并。本次完整测试的具体结果观察于 Windows / Python 3.13。

## 报告与原始数据

[HTML 报告](report.html)来自真实 trace 的审阅后派生版本，包含工具回执、替换片段、
更大范围的失败测试和未完成状态。本机路径已替换为占位符，原始 trace 与工作区保留在本地。
未捕获完整模型 I/O；公开附件 SHA-256 见[证据清单](evidence.json)。

更简单的“验证过 / 未验证”对比仍可在[脚本化演示](https://hwfengcs.github.io/DM-Code-Agent/)中体验。
自己的仓库任务从[快速开始](../../getting-started.md)进入。
