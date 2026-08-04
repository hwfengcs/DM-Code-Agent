# DM-Code-Agent 接手 prompt

> 直接把下面整段（从 `---` 之后）粘进新对话即可。

---

接手 DM-Code-Agent（`C:\Users\ECNU\Desktop\DM\DM-Code-Agent`），先读 `CLAUDE.md`。
中文交流。

## 一、这个项目现在是什么

本地优先、可审计的 Python Code Agent（ReAct + Planner + Replan + append-only 会话日志）。
内核 `dm_agent/core/agent.py` 只做装配 + 主循环（847 行），可选能力全部挂在六个生命周期
钩子上。**记分牌是自带的 30 题 hidden-test benchmark**，不是 SWE-bench。

## 二、最近做完的四件事（都在 main 上）

1. **减法重构**（devlog 33）：删掉 SWE-bench Lite、Reflexion / Critic /
   Self-Consistency、工具熔断、记忆卫生、LLM 摘要压缩共 6 个"毕业标准依赖已冻结评测、
   因而永远无法证伪"的模块，净删约 7000 行，CLI 开关 35 → 23，
   `dm_agent/extensions/capabilities/` 子包整个移除。
2. **记分牌可用化**（devlog 34）：`--suite all`（30 题出一个总分）+
   `dm-agent-score-diff`（逐题 pass/fail 翻转、回归即使总分上升也单独列出、
   噪声口径直接印在输出里、任务集不同时拒绝比较并 exit 2）。
3. **评测集 13 → 30 题**（devlog 34）：noise floor 从 ±7.7 降到 ±3.3 个百分点。
4. **Claude Code (Opus 5) vs DeepSeek + dm-agent 同题对局**（devlog 35）。

## 三、当前最重要的发现 —— 下一步工作的全部依据

同样 13 题、同样判分逻辑：

| | pass_rate |
| --- | --- |
| Claude Code + Opus 5 | 7/13 = 0.538 |
| DeepSeek + dm-agent | 5/13 = 0.385 |

差 2 题，在 13 题噪声下够不上显著。**但真正的信号在这里**——Claude 跑全 30 题：

```
coding      15/15    ← 对前沿模型已饱和，无区分度
maintenance  4/15
总分        19/30 = 0.633
隐藏测试    28/30 = 0.933   ← 与总分差 30 个百分点
```

**11 个失败里 10 个是「改了不该改的文件」**（9 题去改 `tests/test_public_*.py`，
1 题新建 `conftest.py`）。DeepSeek 的 baseline 里这也是首要失败模式（8 个失败中 3 个）。

> **结论：瓶颈不是写不出代码，是不守 `allowed_changed_files` 约束。**
> 换更强的模型不但没消除这个失败模式，占比反而更高——因为"写不出代码"的失败全消失了。

## 四、请按顺序做

### 第一步：消融实验（便宜，必须先做）

把每题的 `allowed_changed_files` 明确写进 `task.prompt`（改
`dm_agent/benchmarks/tasks.py` 的 prompt 模板即可），重跑 DeepSeek baseline，
用 `dm-agent-score-diff` 对比既有 baseline。

- 若违规大幅下降 → 是**提示问题**，改 prompt 模板收工，不需要第二步
- 若不降 → 是 agent **自控问题**，做第二步

注意：改 prompt 会改变 `suite_signature`，`score-diff` 会拒绝跨任务集比较。
所以这一步要比的是**违规题数**，不是 pass_rate；或者另存一份 manifest 再比。

### 第二步：写外部扩展（仅当第一步证明需要）

在 `before_tool_call` 上拦下对 `allowed_changed_files` 之外文件的写入。
**不要改内核**——参考 `docs/extensions.md` 与 `docs/lifecycle-events.md`，
放 `~/.dm_agent/extensions/*.py` 或用 `--extension PATH` 传入。
改完用 `score-diff` 量化收益，写 devlog 36。

### 第三步（可选）

- maintenance 继续加题（coding 已饱和，别再加）
- 补齐跨模型对照

## 五、硬约束（违反会被 CI 或架构测试拦下）

- 中文交流；提交用 Conventional Commit（`feat:` / `fix:` / `refactor:` / `bench:` / `docs:` / `chore:`）
- **改动完成前必须全绿**：
  ```
  python -m pytest                     # 441 passed
  python -m dm_agent.evals.cli --output r.json && python -m dm_agent.evals.gate r.json --min-success-rate 1.0
  python -m ruff check . && python -m black --check . && python -m mypy dm_agent
  uv lock --check
  # 两条 manifest guard（CI 同款）
  python -m dm_agent.benchmarks.cli --suite coding --manifest-only a.json
  python -m dm_agent.benchmarks.manifest_diff bench_reports/manifest-baseline-coding.json a.json
  ```
- **加 benchmark 题必须守三条不变量**：① 初始工作区下隐藏测试必须失败；
  ② 隐藏测试文件不得进 `allowed_changed_files`；③ 题目必须可解——前两条有单测，
  第三条要手写参考解验证（`prepare_workspace` → 写入参考解 → `run_hidden_tests` 应为 0）
- **判分/注入隐藏测试只能用 `_write_files(ws, task.hidden_files)`**，
  绝不能用 `prepare_workspace(..., include_hidden=True)`——后者会先重写 `setup_files`，
  把 agent 的成果整个覆盖回初始版本。这个坑让我作废过一整轮 30 题实验。
- **不要重新引入已删的 6 个模块**。要复活就写成外部扩展；`AgentCapability` 协议和
  六个钩子都原样保留着。
- 任务集变更会改 `suite_signature`，CI 的 manifest guard 会 fail —— 那是它按设计工作，
  重新生成 `bench_reports/manifest-baseline-*.json` 即可
- 路径一律走 `dm_agent/paths.py`，绝不能用 `Path(__file__).parents[N]`

## 六、关键文件位置

| 用途 | 路径 |
| --- | --- |
| 评测数据集（30 题，无外部数据文件） | `dm_agent/benchmarks/tasks.py` |
| 判分逻辑 | `dm_agent/benchmarks/runner.py` 的 `_score_run` |
| 分数对比工具 | `dm_agent/benchmarks/score_diff.py` |
| DeepSeek baseline（13 题） | `bench_reports/baseline-20260803.json` |
| DeepSeek baseline（30 题） | `bench_reports/baseline-30task-20260804.json` |
| Claude arena 结果（30 题） | `bench_reports/arena-claude-opus5-20260803.json` |
| 设计决策记录 | `docs/research-log/33..35` |

## 七、状态

`main` 分支，工作树干净，全部检查绿。是否 push 由用户决定（此前用户自行 push 过一次）。
