# DM-Code-Agent 接手 prompt

> 直接把下面整段（从 `---` 之后）粘进新对话即可。

---

接手 DM-Code-Agent（`C:\Users\ECNU\Desktop\DM\DM-Code-Agent`），先读 `CLAUDE.md`。
中文交流。

## 一、这个项目现在是什么

本地优先、可审计的 Python Code Agent（ReAct + Planner + Replan + append-only 会话日志）。
内核 `dm_agent/core/agent.py` 只做装配 + 主循环，可选能力挂在六个生命周期钩子上。
**记分牌是自带的 30 题 hidden-test benchmark**（coding 15 + maintenance 15），不是 SWE-bench。

## 二、最近三轮实验（devlog 36/37/38，都在 main 上，**未 push**）

一条完整的因果链，每轮都用 `dm-agent-score-diff` 量化。全部 DeepSeek `deepseek-chat`、
temperature 0、variant `full`、30 题各跑一次。

| 轮次 | 干预 | pass_rate | 结论 |
| --- | --- | ---: | --- |
| baseline | — | 0.500 (15/30) | hidden 0.900，落差 40 点全是过程纪律 |
| **36** | `--declare-allowed-files` | **0.733** | **有效**：违规 8 题 → **0** |
| **37** | `--max-steps 30` | 0.800 | **无效**（负面结果），已存档不采用 |
| **38** | 修 `edit_file` | **0.833** | **有效**：编辑自伤 13 次 → **0** |

### devlog 36：约束从来没写进 prompt

`allowed_changed_files` 从没进过交给 agent 的 prompt，而 `MAINTENANCE_PROMPT_SUFFIX`
还有一句 "update tests when the task asks for a regression test" 在反向诱导。
8 道违规题 100% 是改 `tests/test_public_*.py`，且 8/8 的隐藏测试本来就是绿的。
**把规则说出来 → 违规归零**，devlog 35 推断的「要写 `before_tool_call` 守卫扩展」被证伪。

实现要点：开关走 `BenchmarkRunConfig.declare_allowed_files` + `BenchmarkTask.scoped_prompt()`
派生视图，**刻意不碰 `task.prompt`** —— 指纹不变 → `suite_signature` 不变 → score-diff
能直接比 pass_rate、manifest baseline 不用重生成。有单测锁死这条。

### devlog 37：步数预算是假瓶颈（负面结果）

4 道步数耗尽题里，3 题在实验组只用了 **9/13/16 步**就通过 —— **低于它们原来的上限**，
预算根本没绑定；唯一吃到超额预算的 `packaging_ci_contract`（21 步）仍然失败。
翻转 10 题、噪声底 ±3 题，+6.7 点不构成证据。放宽预算反让自伤 13 → 25 次、token +30.6%。

**真病因**：`edit_file` 的 `replace` 执行 `lines[start:end] = [content]`，区间给宽一行就
静默吞掉相邻代码；旧回执只有一句「已替换第 N-M 行」，实测平均 **2.2 步**后才发现，
再花 3–6 步修自己（常常再错一次）。6/30 题踩到，**占失败题的一半**。

### devlog 38：修 edit_file（当前 HEAD 的状态）

两处干预：`old_string`/`new_string` 按内容定位（必须逐字命中且仅一次，0 处或多处则
**一个字节都不写**）+ 每次编辑后回显受影响区间（带新行号、标出改动行、±3 行、上限 40 行）
+ `.py` 过 `ast.parse`（**只报告不回滚**）。

| 主指标 | 前 | 后 |
| --- | ---: | ---: |
| 编辑自伤 | 13 次 / 6 题 | **0 次 / 0 题** |
| `old_string` 采用率 | — | **47/47 = 100%，零未命中** |
| `edit_file` 调用 | 63 | 47（−25%） |
| 总步数 / token | 350 | 325（−7.1%）/ −3.9% |

devlog 37 的诊断被验证：`semver_compare` 16 步用满 → 14 步 PASS；
`cli_config_docs_contract` 18 步用满 → **9 步** PASS；`packaging_ci_contract` 不再耗尽，
露出真实死因（隐藏测试没过）。

## 三、当前状态与剩余失败

`editfix-20260804.json`：**25/30 = 0.833**，hidden 0.933，违规 0。剩 5 题：

| 任务 | 原因 | 隐藏测试 |
| --- | --- | --- |
| `cross_file_user_contract` | 步数耗尽 | **通过** |
| `filename_sanitizer` | 步数耗尽 | **通过** |
| `normalize_users` | 步数耗尽 | **通过** |
| `packaging_ci_contract` | 隐藏测试没过 | — |
| `patch_summary_name_status` | 隐藏测试没过 | — |

后两题是真实能力不足。前三题代码都写对了没走到 `finish`，但
**devlog 37 已证明加预算无效** —— 别再走那条路。

## 四、三条方法论教训（比任何单个分数都重要）

1. **主指标必须挑不受 pass/fail 噪声影响的直接计数。** 三轮分别是违规题数、实际用了
   多少步、自伤次数。pass_rate 在 30 题下永远说明不了 4 题以内的事。
2. **实测噪声底是 ±3 题 ≈ ±10 个百分点**，不是 devlog 34 按题数算的 ±3.3。证据：
   prompt 逐字未变的 coding 题翻转了 3 题；且 `max_steps` 确实不进 prompt
   （`prompting`/`context_window`/`RunContext`/`planner` 四处都核对过），
   而原本 6 步通过的题下一轮用了 11 步。**单轮 + 小于 3 题的差异不构成证据。**
3. **负面结果和自我更正照样存档**，并在被证伪的原文标注更正（35→36、37→38 都这么做）。

## 五、下一步（按杠杆排序）

用户的目标是**找大厂 agent 算法工程师岗位**，这决定优先级。上一轮的评估：方法论 8 分、
工程规范 8 分，但**评测的行业可比性只有 3 分** —— 缺一个能和公开数字对齐的坐标。

### 第一优先：重跑 SWE-bench Verified 子集（最高性价比）

SWE-bench Lite 子系统在 devlog 33 被整个移除，理由是跑不通（Tier-1 resolved 0.0%、
Tier-2 verifier 从未实现）。**但那个判断是在两个已修复的缺陷之下做出的**：
当时既没有约束声明、`edit_file` 也还在自伤。现在两个都修了，值得重新验证一次。

- 目标：跑通 SWE-bench Verified 的 50–100 题子集，拿到任何一个非零的可比数字
- 取回方式见 `docs/research-log/33-scope-reduction.md`（写了怎么复活）
- 守 CLAUDE.md 的宪法：**要复活就写成外部扩展或独立子系统，不要往内核塞**
- 即使只有 5–10%，配上现有方法论叙事，说服力也会跳一档

### 第二优先：补 `--repeat 3`

把「噪声底 ±3 题」从一句观察坐实成可引用的数字。约 450 万 token / 50 分钟。
价值不在提分，在于能说出「我知道我的 benchmark 分辨率极限是 10%」。

### 第三优先：还 `is_failure_observation` 的债

`core/observation.py` 的 `FAILURE_MARKERS` 用**裸子串匹配 `error`**，导致回显了
`from errors import NotFound` 的**成功**编辑被判成失败观察、白烧一次 planner 调用。
实测 78 次 replan 里 **17 次（22%）是这种误报**。根因早于 devlog 38（`read_file` 一直如此）。
修法：把判定限制在工具自己写的**结构化前缀**而非全文扫描；或给护栏文案显式标记位。

### 可选

- 写一篇公开复盘（`hidden−pass` 落差指标 + 三次消融 + 两次自我证伪），现在全埋在仓库里
- maintenance 继续加题（coding 对前沿模型已饱和，别再加）

## 六、硬约束（违反会返工或被 CI 拦下）

- 中文交流；Conventional Commit（`feat:` / `fix:` / `refactor:` / `bench:` / `docs:` / `chore:`）
- **改动完成前必须全绿**：
  ```
  python -m pytest                     # 当前 454 passed
  python -m dm_agent.evals.cli --output r.json && python -m dm_agent.evals.gate r.json --min-success-rate 1.0
  python -m ruff check . && python -m black --check . && python -m mypy dm_agent
  uv lock --check
  python -m dm_agent.benchmarks.cli --suite coding --manifest-only a.json
  python -m dm_agent.benchmarks.manifest_diff bench_reports/manifest-baseline-coding.json a.json
  ```
- **`bench_reports/` 在 .gitignore 里**，存档报告要 `git add -f`；traces 目录**不入库**
- **判分/注入隐藏测试只能用 `_write_files(ws, task.hidden_files)`**，绝不能用
  `prepare_workspace(..., include_hidden=True)` —— 后者会先重写 `setup_files`，
  把 agent 的成果整个覆盖回初始版本。这个坑作废过一整轮 30 题实验且不可恢复
- **内核护栏与工具的提示文案必须避开 `FAILURE_MARKERS`**（失败/错误/error/不存在），
  否则局部可纠正的问题会白烧一次 planner 调用。参照 `core/guards.py:_block_message`
- **加 benchmark 题守三条不变量**：① 初始工作区下隐藏测试必须失败；② 隐藏测试文件
  不得进 `allowed_changed_files`；③ 题目必须可解（手写参考解验证）
- 任务集变更会改 `suite_signature`，CI 的 manifest guard 会 fail —— 那是按设计工作，
  重新生成 `bench_reports/manifest-baseline-*.json` 即可
- 路径一律走 `dm_agent/paths.py`，绝不能用 `Path(__file__).parents[N]`
- **不要重新引入 devlog 33 删掉的 6 个模块**（Reflexion / Critic / Self-Consistency /
  熔断 / 记忆卫生 / LLM 摘要压缩）。要复活就写成外部扩展

## 七、关键文件位置

| 用途 | 路径 |
| --- | --- |
| 评测数据集（30 题，无外部数据文件） | `dm_agent/benchmarks/tasks.py` |
| 判分逻辑 | `dm_agent/benchmarks/runner.py` 的 `_score_run` |
| 约束声明开关 | `models.py:BenchmarkTask.scoped_prompt()` + `declare_allowed_files` |
| `edit_file` 实现 | `dm_agent/tools/file_tools.py` |
| 失败观察判定（有债） | `dm_agent/core/observation.py` |
| 分数对比工具 | `dm_agent/benchmarks/score_diff.py` |
| DeepSeek baseline（30 题，0.500） | `bench_reports/baseline-30task-20260804.json` |
| 约束声明组（0.733） | `bench_reports/ablation-scope-20260804.json` |
| 步数实验（0.800，**不采用**） | `bench_reports/steps30-20260804.json` |
| edit_file 修复后（0.833，**当前水位**） | `bench_reports/editfix-20260804.json` |
| Claude arena（30 题，0.633） | `bench_reports/arena-claude-opus5-20260803.json` |
| 设计决策记录 | `docs/research-log/33..38` |

## 八、状态

`main` 分支，工作树干净，全部检查绿（454 passed、eval gate 1.000、两条 manifest guard
`compatible`、pre-commit 四钩子）。**8 个 commit 未 push**（`cfe0d3a`..`62493fe`），
是否 push 由用户决定。

复现任一轮实验（需 `.env` 里的 `DEEPSEEK_API_KEY`，约 15 分钟 / 150 万 token）：

```bash
python -m dm_agent.benchmarks.cli --suite all --declare-allowed-files \
  --trace-dir bench_reports/<name>-traces \
  --output bench_reports/<name>.json --markdown bench_reports/<name>.md

python -m dm_agent.benchmarks.score_diff \
  bench_reports/editfix-20260804.json bench_reports/<name>.json
```
