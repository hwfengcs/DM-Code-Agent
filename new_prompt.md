# DM-Code-Agent 接手 prompt

> 直接把下面整段（从 `---` 之后）粘进新对话即可。

---

接手 DM-Code-Agent（`C:\Users\ECNU\Desktop\DM\DM-Code-Agent`），先读 `CLAUDE.md`。
中文交流。

## 一、这个项目现在是什么

本地优先、可审计的 Python Code Agent（ReAct + Planner + Replan + append-only 会话日志）。
内核 `dm_agent/core/agent.py` 只做装配 + 主循环，可选能力挂在六个生命周期钩子上。

两个记分牌：

- **自带 30 题 hidden-test benchmark**（coding 15 + maintenance 15）——主力，衡量过程纪律
- **SWE-bench Verified**（`swebench_verified/`，2026-08-05 建）——独立子系统，
  判分交给官方 harness，用来拿一个能和公开数字对齐的坐标

## 二、四轮实验（devlog 36/37/38/39，都在 `main` 上）

一条完整的因果链。全部 DeepSeek `deepseek-chat`、temperature 0、variant `full`。

| 轮次 | 干预 | pass_rate | 结论 |
| --- | --- | ---: | --- |
| baseline | — | 0.500 | hidden 0.900，落差 40 点全是过程纪律 |
| **36** | `--declare-allowed-files` | 0.733 | **有效**：违规 8 题 → 0 |
| **37** | `--max-steps 30` | 0.800 | **无效**（负面结果），已存档不采用 |
| **38** | 修 `edit_file` | 0.833 | **有效**：编辑自伤 13 次 → 0 |
| **39** | 修失败判定 + `run_linter` | **0.878**（repeat 3） | **有效**：误报 replan 34 → 0 |

前三轮的详情见 devlog；下面只写第 39 轮和它翻出来的东西。

### devlog 39：失败判定在扫描工具搬运的内容

`core/observation.py` 的 `FAILURE_MARKERS` 里躺着裸子串 `error`。观察文本混着两种东西——
工具**自述**的状态（`文件 x 不存在。`）和工具**搬运**的外部内容（文件正文、stdout）——
全文扫描对两者一视同仁，于是读到 `from errors import NotFound` 就把一次成功的 read_file
判成失败，白烧一次 planner 调用。

复算 devlog 38 那轮的 30 份 trace：**78 次 replan 里 34 次（43.6%）是误报**。
（devlog 38 的「代价栏」记的 17 次是"回显触发"这一个口径，不是全部误报，两者不矛盾。）

改为按来源分层：内核前缀 → 语法检查未通过 → **退出码为权威信号** → 工具自述句式 →
内置工具默认不失败 → 第三方工具仍全文扫描（保持兼容）。同一批 trace 复算：
**误报 38 → 0，46 次真失败全保住，另多抓到 4 次旧判定漏判的**，零反向误报。

顺带修掉两个：

- **`run_linter` 撞墙**：默认硬编码 flake8 而环境装的是 ruff，39 次调用 **29 次**撞
  `No module named`、横跨 **15/30 题**，占该轮 8.9% 的步数。改为报出本环境可用清单 → **0**。
- **Windows 行尾**（跑 SWE-bench 才暴露）：`Path.write_text` 默认按平台改写行尾，
  编辑 LF 文件会把整份文件转 CRLF。astropy 上改一处逻辑，patch 从 504 B `+1/-1`
  变成 20595 B `+317/-317`。本地 benchmark 测不出——工作区文件都是新建的。

### 首次 `--repeat 3`：单轮说谎

单轮 pass_rate 掉了 6.7 点（0.833 → 0.767），看着像回归。跑 90 次 run 后：

| 分类 | 题数 |
| --- | ---: |
| 3/3 稳定通过 | 24 |
| 2/3 抖动 | 4 |
| 0/3 稳定失败 | 2 |

- **真实水位 0.878**，单轮抽到的是运气差的一次
- `pass@3 = 0.933` vs `pass^3 = 0.767`，**5 题在多轮之间来回翻**
- 抖动的 4 题里 3 题正是单轮里"回归"的那批——不是回归，是抖动
- 原先步数耗尽的 3 题现在全部 3/3 通过：**误报重规划吃掉的步数就是它们的死因**，
  这回过头解释了 devlog 37「加预算无效」为什么是对的

## 三、当前状态

`obsfix-r3-20260805.json`：**0.878**（3 次平均）。稳定失败只剩 2 题，都是真实能力不足：

| 任务 | 状态 |
| --- | --- |
| `packaging_ci_contract` | 0/3，隐藏测试没过 |
| `patch_summary_name_status` | 0/3，隐藏测试没过 |

**SWE-bench Verified 首个可比数字：10 题 resolved 2 = 20%**
（`bench_reports/swebench-verified-10-20260805.json`，判分完全由官方 swebench 4.1.0 完成）。
6 道 unresolved 里多数是"没修好"而非"改坏了"：13236 的 PASS_TO_PASS 是 644/644、
14182 是 9/9，零回归；13977 已修好 F2P 12/20。只有 13453 明显改坏原行为。
2 题 60 步耗尽出空 patch。

> 这 10 题按数据集顺序取前 N，**全部来自 astropy 单一仓库**，不构成对整体的估计。
> 扩子集时要改成跨仓库抽样。

## 四、四条方法论教训（比任何单个分数都重要）

1. **主指标必须挑不受 pass/fail 噪声影响的直接计数。** 四轮分别是：违规题数、实际用了
   多少步、自伤次数、误报 replan 次数 + 撞墙次数。四轮结论站得住靠的一直是这条。
2. **实测噪声底是 ±5 题 ≈ ±16.7 个百分点**（首次 repeat 3 实测），不是 devlog 37 观察
   的 ±3、更不是 devlog 34 按题数算的 ±3.3。**30 题这个盘子测不出 5 题以内的改进。**
3. **负面结果和自我更正照样存档**，并在被证伪的原文标注更正（35→36、37→38、37/38→39
   都这么做；devlog 39 还更正了自己初稿的两句错话）。
4. **自建 benchmark 有系统性盲区。** Windows 行尾缺陷在 30 题上永远测不出来——那些工作区
   文件都是新建的、行尾自始至终一致。**要有一个外部的真实仓库才暴露得出来。**

## 五、下一步（按杠杆排序）

用户的目标是**找大厂 agent 算法工程师岗位**，这决定优先级。下面三条已经做过初步
诊断，证据都在，可以直接接着干。

### 第一优先：治空 patch —— 10 题里 2 题跑满 60 步一个字没写

这是当前最直接的失分项：**救回这 2 题就是 +20%**，而且成本远低于扩子集。
已经挖到根因，两题的失败模式**完全不同**，要分开治：

**A. `astropy-13579`：edit guard 的 stale_read 把 agent 卡进循环**

22 次 `edit_file` 里 **11 次成功、11 次被守卫拦下**：

```
Edit blocked: astropy/wcs/wcsapi/wrappers/sliced_wcs.py changed after your
last read in this run. Re-read the target range with read_file ...
```

模式是「改一次 → 文件变了 → 下次编辑被判 stale → 重读 → 再改」，一半的编辑预算
花在重读上。更糟的是成功那几次的回执写着 **`1146 -> 1146 字符`**——字符数一个没变，
说明 agent 在**把同一段代码改来改去，最后改回了原样**，所以 patch 是空的。

要查的东西：`core/guards.py` 的 stale_read 判定是不是对「同一个 run 内自己刚写过
的文件」也算 stale。如果是，那对连续编辑同一文件的场景就是纯损耗——agent 自己写的
改动，它当然知道内容。注意别把守卫整个关掉，devlog 里它挡住过真实的行号漂移。

**B. `astropy-14096`：29 次 `read_file`、0 次编辑，探索瘫痪**

60 步全在读文件，从头到尾没尝试过一次编辑。这跟 A 是两回事，先看 trace 里的
thought 序列判断它在犹豫什么——是定位不到目标文件，还是反复确认不敢下手。

```bash
python -m dm_agent.tracing.cli view swebench_work/traces-10/astropy__astropy-14096.jsonl
```

（trace 目录不入库，需要重跑一遍预测才有；命令见第八节。）

**验收标准**：主指标是**空 patch 数**（2 → 0）与**被守卫拦下的编辑次数**，
都是直接计数，不受 resolve 率噪声影响——按教训 1 办。

### 第二优先：把 SWE-bench 子集扩到跨仓库 50 题

10 题已出数（resolved 2/10），但**全部来自 astropy**，代表性不足，不能拿去对外说。

要改的地方：`swebench_verified/dataset.py` 的 `fetch_instances()` 现在是**按数据集
顺序取前 N**（数据集按 instance_id 字典序排，所以前 10 条必然同一个仓库）。
应改成**按 repo 分层抽样**，且保持确定性（同一个 `--limit` 换机器换时间拿到同一批题，
否则报告之间不可比）。数据里有 `repo` 与 `difficulty` 两个字段可用。

成本实测：

| 项 | 量级 |
| --- | --- |
| 镜像 | 约 3.9 GB / 题，但**层是共享的**：10 题实际只占 7.3 GB |
| 预测 | 30 秒 – 19 分钟 / 题（抖动极大，见下） |
| 判分 | 约 20 秒 / 题 |

跨仓库会比 astropy 内部更费磁盘（层共享变少），先看 `docker system df` 再决定规模。

**判读时先扣掉抖动**：SWE-bench 上的轨迹抖动比 30 题 benchmark 大得多——同一道
`astropy-12907`、同样配置，一次 8 步 success、一次 60 步耗尽。小样本 resolve 率
的差异基本说明不了问题。

### 第三优先：给 maintenance 加题

30 题这个盘子测不出 5 题以内的改进（教训 2），要么加题要么每次都 `--repeat 3`。
coding 对前沿模型已饱和（Claude 15/15），**只往 maintenance 加**。加题守第六节
那三条不变量，并记得重新生成 `bench_reports/manifest-baseline-*.json`。

### 可选：写一篇公开复盘

现在全埋在仓库里。手上已经有的材料：`hidden−pass` 落差指标、四次消融（两次有效、
一次负面结果、一次翻盘）、三次自我证伪、一次「修好 A 放大了 B」的因果链，
外加一个「系统性环境故障伪装成 agent 能力极差」的实例（P2P 全 0）。

## 六、硬约束（违反会返工或被 CI 拦下）

- 中文交流；Conventional Commit（`feat:` / `fix:` / `refactor:` / `bench:` / `docs:` / `chore:`）
- **改动完成前必须全绿**：
  ```
  python -m pytest                     # 当前 476 passed
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
- **内核护栏与工具的提示文案仍应避开 `FAILURE_MARKERS`**。devlog 39 后该清单只对
  第三方扩展工具生效，内置工具走精确判定；但新增内置工具时要确认其失败自述符合
  `_TOOL_REFUSAL_RE` / `returncode` 契约，`tests/test_observation_failure.py` 有断言把关
- **加 benchmark 题守三条不变量**：① 初始工作区下隐藏测试必须失败；② 隐藏测试文件
  不得进 `allowed_changed_files`；③ 题目必须可解（手写参考解验证）
- 任务集变更会改 `suite_signature`，CI 的 manifest guard 会 fail —— 那是按设计工作，
  重新生成 `bench_reports/manifest-baseline-*.json` 即可
- 路径一律走 `dm_agent/paths.py`，绝不能用 `Path(__file__).parents[N]`
- **不要重新引入 devlog 33 删掉的 6 个模块**（Reflexion / Critic / Self-Consistency /
  熔断 / 记忆卫生 / LLM 摘要压缩）。要复活就写成外部扩展或独立子系统——
  `swebench_verified/` 就是照这条做的样板
- **SWE-bench 四个会让分数无效的坑**见 `swebench_verified/README.md`：工作区必须放系统
  临时目录（否则 agent 会爬父目录读走 `FAIL_TO_PASS`）、`core.fileMode`/`autocrlf` 必须
  关、`_assert_git_root` 安全闸不要移除、`evaluate.py:force_lf_writes()` 不要删
  （官方 harness 在 Windows 上把 `/eval.sh` 写成 CRLF，容器里一条命令都跑不了，
  症状是 **PASS_TO_PASS 全 0**，看着像 agent 把模块改坏了）

## 七、关键文件位置

| 用途 | 路径 |
| --- | --- |
| 评测数据集（30 题，无外部数据文件） | `dm_agent/benchmarks/tasks.py` |
| 判分逻辑 | `dm_agent/benchmarks/runner.py` 的 `_score_run` |
| 约束声明开关 | `models.py:BenchmarkTask.scoped_prompt()` + `declare_allowed_files` |
| `edit_file` 实现 / 行尾处理 | `dm_agent/tools/file_tools.py` |
| 失败观察判定（已修） | `dm_agent/core/observation.py` |
| SWE-bench 子系统 | `swebench_verified/`（含 README 与四个坑） |
| 分数对比工具 | `dm_agent/benchmarks/score_diff.py` |
| DeepSeek baseline（0.500） | `bench_reports/baseline-30task-20260804.json` |
| 约束声明组（0.733） | `bench_reports/ablation-scope-20260804.json` |
| 步数实验（0.800，**不采用**） | `bench_reports/steps30-20260804.json` |
| edit_file 修复后（0.833） | `bench_reports/editfix-20260804.json` |
| 判定修复后单轮（0.767） | `bench_reports/obsfix-20260805.json` |
| **判定修复后 repeat 3（0.878，当前水位）** | `bench_reports/obsfix-r3-20260805.json` |
| **SWE-bench Verified 10 题（resolved 2/10）** | `bench_reports/swebench-verified-10-20260805.json` |
| Claude arena（30 题，0.633） | `bench_reports/arena-claude-opus5-20260803.json` |
| 设计决策记录 | `docs/research-log/33..39` |

## 八、状态

`main` 分支，工作树干净，全部检查绿（476 passed、eval gate 1.000、两条 manifest guard
`match`、pre-commit 四钩子全 Passed）。**5 个 commit 未 push**（至 `762c7a3`），
是否 push 由用户决定。

复现 30 题实验（需 `.env` 里的 `DEEPSEEK_API_KEY`）：

```bash
# 单轮，约 15 分钟 / 130 万 token
python -m dm_agent.benchmarks.cli --suite all --declare-allowed-files \
  --trace-dir bench_reports/<name>-traces \
  --output bench_reports/<name>.json --markdown bench_reports/<name>.md

# 带误差棒，约 50 分钟 / 400 万 token（判读小于 5 题的差异时必须用这个）
python -m dm_agent.benchmarks.cli --suite all --declare-allowed-files --repeat 3 \
  --trace-dir bench_reports/<name>-r3-traces --output bench_reports/<name>-r3.json

python -m dm_agent.benchmarks.score_diff \
  bench_reports/obsfix-r3-20260805.json bench_reports/<name>.json
```

跑 SWE-bench Verified（需 Docker Desktop 运行中；daemon 挂了脚本会带原因早退）：

```bash
# 预测。--trace-dir 一定要给：治空 patch 那条要靠 trace 诊断，而 trace 不入库。
# --resume 可续跑，且只重试 harness_error，不会把环境失败当"已完成"跳过。
python -m swebench_verified.run --limit 10 --max-steps 60 --resume \
  --output swebench_work/preds.jsonl --trace-dir swebench_work/traces

# 判分。必须在 .swebench-venv 里跑，且必须带 PYTHONPATH（Windows 垫片）。
PYTHONPATH=swebench_verified/_winshim \
  .swebench-venv/Scripts/python.exe -m swebench_verified.evaluate \
  --predictions swebench_work/preds.jsonl --run-id myrun --max-workers 4
```

判分完会写 `dm-agent-<provider>.<run_id>.json`，逐题结果在
`logs/run_evaluation/<run_id>/`（含 `patch.diff`、`eval.sh`、`test_output.txt`，
诊断全靠它们）。**两者都在 .gitignore 里，要存档得 `git add -f`。**
