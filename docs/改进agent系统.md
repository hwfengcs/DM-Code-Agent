# 改进 agent 系统：可执行方案

- 撰写日期：2026-08-08（v2，取代 v1 初稿）
- 基线：`bench_reports/swebench-verified-crossrepo-50-*`（DeepSeek `deepseek-chat`、
  temperature 0、`--max-steps 60`、官方 swebench 4.1.0 判分）
- 基线分数：**resolved 21/50 = 42%**，empty patch 7，harness error 0

> **样本边界**：本文全部诊断数字来自上述这一次真实运行的 50 题 predictions + 50 份
> trace + 官方 report。20 题是 50 题的严格前缀，不是独立复验。本文提出的改进
> **尚未运行**，所有"预期收益"均为假设，每项都附证伪判据；**在实测之前，不得把任何
> 预期数字写进 README、CHANGELOG 或对外材料**。

---

## 给执行者的开场

你将按本文改造 `swebench_verified/` 子系统。开工前**必须**读完：

| 文件 | 为什么 |
| --- | --- |
| `CLAUDE.md` | 项目宪法。内核最小化、分层契约、语言约定 |
| `swebench_verified/README.md` | 评测子系统契约与**六个已知坑**，改错任一个分数即无效 |
| `docs/lifecycle-events.md` | 钩子语义与三条陷阱（尤其"改参数后不会重新校验""处理器抛异常等价于放行"） |
| `docs/extensions.md` | 扩展与能力的安全模型 |
| `docs/research-log/40-empty-patch-loops.md` | 上一轮空 patch 治理与**定向复跑的先例格式** |
| `docs/research-log/42-swebench-crossrepo-50.md` | 本文基线运行的完整记录 |

### 五条不可违反的红线

1. **判分永远交给官方 harness。** 不写自己的 verifier，不自己判 resolved。
2. **不动 `dm_agent/` 内核。** 所有新增能力住在 `swebench_verified/` 下，经
   `capabilities=[...]` 或工具替换装配。不新增 `--enable-xxx` 内核开关。
3. **不重新引入 Reflexion / Critic / Self-Consistency / 熔断**（devlog 33 已删，
   毕业标准依赖已冻结的评测，无法证伪）。
4. **不改 `pyproject.toml` / `uv.lock`。** 子系统只用标准库 + 已有依赖 + subprocess 调 docker。
5. **诊断字段缺失 = 未测量 ≠ 0。** 新增字段必须写**新** output 验收，不能用 `--resume`
   静默保留旧记录。

### 每个阶段的交付清单（逐条打勾，缺一不算完成）

- [ ] 实现 + 单元测试（`tests/` 下，**不得引入网络调用、不得依赖 Docker、不得需要 API key**）
- [ ] `python -m pytest` / `ruff check .` / `black --check .` / `mypy dm_agent` 全绿
- [ ] 本阶段的验收命令跑过，产出归档
- [ ] `docs/research-log/NN-slug.md` 留 devlog 并链入 `docs/research-log/README.md`
- [ ] 若结果与证伪判据冲突：**记录否定结果并回退，不修改判据迁就结论**

---

## 0. 一句话结论

当前瓶颈不是"想得不够久"，而是 **agent 无法验证自己的改动是否正确**。
50 题里执行类工具（`run_shell` / `run_python` / `run_tests`）共调用 576 次、
**失败 214 次（37.2%）**，而写入类工具（`edit_file` / `create_file`）调用 113 次、
**失败 0 次**。agent 会改代码，但改完之后拿不到任何真实反馈。

根因只有一个：**agent 跑在 Windows 宿主机上，而代码属于 Linux 容器。**

---

## 1. 现状诊断

### 1.1 分数构成

| dm_status | RESOLVED | UNRESOLVED | EMPTY | 合计 |
| --- | ---: | ---: | ---: | ---: |
| `success`（主动 finish） | **17** | 10 | 0 | 27 |
| `max_steps_exceeded`（跑满 60） | 4 | 12 | 7 | 23 |
| 合计 | 21 | 22 | 7 | 50 |

主动 finish 的 resolved 率 63%，跑满步数的只有 17%。**"跑满步数"是失败信号，不是"差一点"。**

### 1.2 步数已被证明不是瓶颈

21 道 resolved 的步数：`[4,5,5,5,5,5,6,6,7,7,8,9,10,10,15,41,49,60,60,60,60]`，
**中位数 8，15 道在 10 步内完成**。

23 道跑满 60 步的题，按"最后一次写文件的步号"分层：

| 最后写入步号 | 题数 | 之后白烧步数 | 说明 |
| ---: | ---: | ---: | --- |
| 0（从未写过） | 7 | 60 | 全部是 empty patch |
| 4 – 20 | 4 | 40 – 56 | 写完后长期漫游 |
| 37 – 58 | 12 | 2 – 23 | 写到很晚，但 patch 是**错的**不是**没写完** |

其中 4 道跑满步数却 resolved 的题，正确 patch 分别写于第 4、20、37、42 步 ——
**没有一例是靠最后几步救回来的**。

结论：加大 `--max-steps` 的预期收益 0–2 题，且成本翻倍（max_steps 组时长中位数
205.4 s vs success 组 47.7 s）。**本方案不含"加大步数"这一项**，详见 §4。

### 1.3 真正的瓶颈：执行类工具失败率

50 份 trace 合计 1613 次工具调用，失败 244 次（**15.1%**）：

| 工具 | 调用 | 失败 | 失败率 |
| --- | ---: | ---: | ---: |
| `read_file` | 529 | 3 | 0.6% |
| `search_in_file` | 349 | 26 | 7.4% |
| **`run_shell`** | **333** | **138** | **41.4%** |
| **`run_python`** | **216** | **50** | **23.1%** |
| `edit_file` | 107 | 0 | **0%** |
| `search_symbol` | 30 | 1 | 3.3% |
| **`run_tests`** | **27** | **26** | **96.3%** |
| `list_directory` | 14 | 0 | 0% |
| `create_file` | 6 | 0 | 0% |
| `run_linter` | 2 | 0 | 0% |

**`run_tests` 27 次调用失败 26 次。** agent 反复尝试验证自己的改动，几乎全军覆没。

### 1.4 138 次 `run_shell` 失败的归因

| 首 token | 次数 | | 错误关键词 | 次数 |
| --- | ---: | --- | --- | ---: |
| `cd` | 48 | | `not recognized`（平台错配） | 47 |
| `python` | 38 | | `cannot find` | 17 |
| `grep` | 19 | | `ModuleNotFoundError` | 14 |
| `findstr` | 10 | | `ImportError` | 11 |
| `pip` | 5 | | `not found` | 4 |
| `pwd` / `git` / `set` / `ls` / `rm` | 14 | | 其他 | 45 |

清晰地分成两桶：

1. **平台错配（约 85 次）**：agent 发 Unix 命令（`grep` / `ls` / `rm` / `cd x && y`）
   给 Windows shell。
2. **环境缺失（约 63 次）**：`python` / `pip` 命中宿主机 Python 3.13.9 + 宿主
   pytest 9.0.2，而不是镜像里的 `testbed` conda 环境。实测样本：

   ```
   matplotlib-25775: ImportError while loading conftest '.../lib/matplotlib/tests/conftest.py'
   django-16950    : platform win32 -- Python 3.13.9, pytest-9.0.2  （仓库依赖不在）
   seaborn-3187    : ~/miniconda3/python.exe                        （错误的解释器）
   ```

**两桶都是同一个根因的两个面。** 修根因即同时消解，见 S1。

### 1.5 越界修改是第二大失分源

跑满步数、有 patch 的 12 道题，按 patch 大小排序后，resolved 的 4 道**恰好是最小的 4 个**：

| patch 大小 | instance | 结局 |
| ---: | --- | --- |
| 11300 B | pytest-5787 | unresolved |
| 7709 B | astropy-13398 | unresolved（**P2P 0/68**） |
| 6605 B | matplotlib-25775 | unresolved |
| 3245 B | sklearn-25102 | unresolved |
| … | | |
| 1589 B | django-12858 | **RESOLVED** |
| 1568 B | xarray-6744 | **RESOLVED** |
| 1103 B | pytest-7236 | **RESOLVED** |
| 395 B | pytest-6202 | **RESOLVED** |

典型案例 `astropy-13398`：主逻辑（`itrs_to_observed` 变换）写得基本正确，但顺手把
`astropy/utils/shapes.py` 里的 `np.core` 改成了 `np._core`。容器里的 numpy 没有
`_core` 属性，导致 astropy 整包 import 失败：

```
AttributeError: module 'numpy' has no attribute '_core'
→ FAIL_TO_PASS 0/4，PASS_TO_PASS 0/68
```

同题还实际改了 `test_icrs_observed_transformations.py`——**`PROMPT_TEMPLATE` 里
第 63 行已明令禁止改测试文件，光靠提示词管不住。**

devlog 42 已记录：新增 30 题中有 **3 道"F2P 全过但引入 P2P 回归"**。
"修到目标测试通过"不等于维护任务完成。

### 1.6 解析失败集中在失败组

| 指标（每题均值） | success 组（27） | max_steps 组（23） | 倍数 |
| --- | ---: | ---: | ---: |
| `dm_parse_errors` | 0.37 | 4.65 | 12.6× |
| `dm_parse_repairs` | 0.93 | **13.13** | 14.1× |
| `dm_replans` | 2.00 | 4.65 | 2.3× |
| `dm_truncations` | 0.30 | 1.57 | 5.2× |
| `dm_repeat_search_blocks` | 0.11 | 2.00 | 18.2× |

单题最差：`astropy-13977` 有 31 次 parse error。

> **因果方向未定**：可能是"陷入困境 → 输出变乱 → 解析失败"，也可能反过来。
> 因此 S0 先做归因，不直接改代码。

---

## 2. v2 相对初稿改了什么（决策记录）

初稿的诊断是对的，六处执行层面的决策不对。这一节说明改动，**执行时以本文为准**。

### 决策 1：排期倒置——治本项提前，被支配项删除

初稿把唯一治本的"容器内执行"排在第 3–4 周，前两周做的三件事全部被它支配：

- P0-C（声明环境不可用 + 拦掉 `run_tests`）：A 落地后**这些工具就能用了**，拦截逻辑要拆掉；
- P0-B（import 冒烟检查）：初稿自己承认宿主执行版本对 `astropy-13398` 那类
  "宿主有 `np._core` 而容器没有"**不一定能复现**——它想抓的头号案例恰好抓不住；
- P4（shell 平台适配）：初稿自己写了"若 A 落地本项自动消失"。

**两周的工作换来一个抓不住头号案例的守卫**，然后被第三周的改动作废。

**v2 处理**：P0-A 升为 S1 并提前；P0-B 降级为 S1 内部的一个子功能（**在容器里跑**，
效力不打折）；P0-C 与 P4 **从计划中删除**，只保留为 S1 判定失败时的回退方案（§5）。

### 决策 2：不用 `before_tool_call` 拦截，改为**在装配处替换工具**

这是初稿最要紧的技术错误。`before_tool_call` 的返回契约只有两种
（`dm_agent/core/events.py:20-33`、`docs/lifecycle-events.md`）：**就地改 `arguments`**，
或返回 `{"block": True, "reason": ...}`。它**无法替换 runner**。

若用 `block` + 把容器输出塞进 `reason` 来"路由"，会撞上内核里这一行
（`dm_agent/core/agent.py:661`）：

```python
no_progress = invocation.blocked or invocation.no_change
```

于是**每一次成功的容器执行都会被计为"无进展"**，planner 不推进计划
（`agent.py:693`），诊断计数也全被污染。这不是风格问题，是会静默败坏实验数据的错误。

**v2 处理**：`predict.py:412` 传的是 `default_tools(include_mcp=False)` —— 一个
普通 list。直接映射替换其中三个同名 `Tool`，runner 换成容器版：

```python
# swebench_verified/container_tools.py
def container_backed_tools(base_tools: list[Tool], container: str) -> list[Tool]:
    """把 run_shell / run_python / run_tests 换成容器内执行的同名工具。

    name 与 description 逐字不变——agent 看到的接口没有任何变化，
    因此不影响 prompt、不影响解析、不影响任何既有诊断字段的语义。
    """
```

钩子留给它真正擅长的事：**写后同步**（S1.3）与**完成前守卫**（S3）。

### 决策 3：定死同步语义——单向 host → container，文件粒度

初稿把这里标为"最大的设计分歧点，动工前必须先定"然后留空了。**现在定死：**

| | 权威方 | 理由 |
| --- | --- | --- |
| **文件内容 / patch** | **宿主工作区** | `extract_patch()` / `_assert_git_root()`（`predict.py:287-350`）整条链路一行不改，六个已知坑的修复全部继续有效 |
| **执行环境** | **容器** | 依赖、解释器、平台都在这里 |

**同步只有一个方向：host → container，写成功后按单文件 `docker cp` 推过去。**
容器内产生的任何东西（`.pyc`、测试输出、`pip install` 的副作用）**永不回流**。

这样做消除了整个冲突解决问题——不存在"两边都改了"的情形，因为容器侧的改动
在设计上就是不被采信的。

**残余风险与其检测**：agent 若用 `run_shell` 在容器内改文件（`sed -i` 之类），
改动不会回到宿主，因此不进 patch。处理方式是**检测并告知，不是静默**：
每次容器内执行后跑一次 `git -C /testbed status --porcelain`，非空则

1. 记 trace 事件 `swebench_container_drift`；
2. 把漂移文件列表**追加进 observation**，明确告诉 agent"容器内的改动不会计入你的
   最终 patch，请用 `edit_file` 在工作区重做"；
3. `docker exec ... git checkout -- .` 把容器恢复到与宿主一致。

### 决策 4：P1 的阈值必须从数据推导，不能拍脑袋

初稿直接给了 15/25/35。但我们**手里没有"首次写入步号"的分布**——1.2 节那张表是
*最后*一次写入，不是第一次。用未测量的量去定阈值，是拿实验成本换一个本来免费就能
得到的数字。

**v2 处理**：S0 先从已归档 trace 离线算出首次写入步号分布，阈值由数据定：
软阈值取 resolved 组首次写入步号的 P90，硬阈值取 P99 或 1.5×P90，取整。
**在 S0 产出该分布之前，不允许写死任何阈值。**

### 决策 5：P2 的测试文件否决改为**自动回退**

初稿设计的是 `before_finish` 硬否决。问题：否决之后 agent 拿什么补救？它得靠
`run_shell` 执行 `git checkout -- <path>`——而 `run_shell` 正是失败率 41.4% 的那个工具。
**一个没有可靠解药的硬否决 = 循环到 max_steps**，把一道 unresolved 变成更差的结局。

**v2 处理**：守卫**自己**执行回退（宿主侧 `git checkout -- <测试文件>`），然后**放行**
finish，并把"已自动撤销 N 个测试文件的改动"写进 observation 与 trace。

正当性：SWE-bench 的规则是 patch 不得含测试文件，官方 harness 会应用它自己的
`test_patch`。**回退测试文件在任何情况下都是正确的**，所以这个动作可以确定性地自动执行，
不需要模型参与。硬否决只保留给"回退本身失败"这一种情况。

### 决策 6：补上能力启用状态的溯源字段

初稿定了"字段缺失 = 未测量"的纪律，却没让 predictions 记录**这一轮开了哪些能力**。
几轮实验之后，归档的 JSONL 将无法区分"这题是在哪个配置下跑的"。

**v2 处理**：`dm_diagnostics_version` 升到 **2**，新增

```
dm_capabilities: ["progress_loop_guard", "container_exec", "patch_scope_guard", ...]  # 有序、去重
dm_exec_backend: "container" | "host"
```

任何新增守卫必须把自己的名字登记进去。缺该字段的记录 = v1 时代的记录 = 未测量。

---

## 3. 执行阶段

四个阶段。**S0 必须最先做**——它零成本、零风险，且为 S2/S3 提供参数。
S1 是唯一治本项。S2/S3 依赖 S0 的产出。

```
S0 离线归因（0 API 成本）──┬─→ S1 容器执行路由（治本）
                          ├─→ S2 无写入预算守卫（阈值来自 S0）
                          └─→ S3 patch 边界守卫（规则由 S0 离线重放验证）
```

---

### S0 — 离线归因与参数标定

**成本**：1–2 天，**0 元 API、不启动 Docker、不联网**。
**风险**：无。
**为什么最先**：它免费，且 S2 的阈值、S3 的规则都要从它的产出里取。

#### S0.1 补三个分析维度

扩展 `swebench_verified/analyze.py`（现有结构见文件头，`_merge_agent` 在 1397 行、
`_trace_output` 在 1448 行）。该模块的既有契约是**离线、不启 Docker、不联网、不构造
LLM client**，必须保持。新增逐题字段：

| 字段 | 定义 | 服务于 |
| --- | --- | --- |
| `first_write_step` | trace 中首个 `action ∈ {edit_file, create_file}` 的 `step_number`，无则 `null` | **S2 阈值标定** |
| `last_write_step` | 同上取最后一个 | 复现 §1.2 表格 |
| `tail_unique_signatures` | 最后 20 步里不同 `(action, arguments)` 签名的数量 | 识别固定点 |

trace 里工具调用由 `SessionWriter.record_tool_call(step_number, action, action_input, …)`
写入，字段齐全。注意 `analyze.py` 已有的规矩：**同一 append-only trace 含多轮复跑时
只读最后一个完整 `run_start` → `run_end` 区间**，新字段必须沿用同一套区间选择。

#### S0.2 解析失败形态分类

从 trace 的 `parse_error` 事件里提取形态，分五类：JSON 截断 / 引号转义 / 多余前后缀
文本 / action 名幻觉 / 参数类型错。

交叉 `parse_error` 的步号与 `observation_truncated` 事件，检验假设：
**长观察 → 上下文膨胀 → 输出被截断 → 解析失败**。

**判据**：只有当某一类占比 **> 40%** 时才提出针对性修复；否则本项结论是
"解析失败是困境的**症状**而非原因"，写进 devlog 后**不再投入**。

#### S0.3 S3 规则的离线重放

50 条归档 predictions 里有完整的 `model_patch` 文本。**不花一分钱**就能把 S3 的
三条规则跑在它们身上：

```powershell
# 输入（全部已归档，只读）
bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl
bench_reports/swebench-verified-crossrepo-50-20260806.json
```

统计：规则会拦下哪些题、其中多少是 unresolved。

**证伪判据**：若"被拦截集合"与"unresolved 集合"的重合度不显著高于随机
（50 题里 unresolved+empty = 29，即基线命中率 58%），规则无效，**S3 取消**。

#### S0 验收

```bash
python -m pytest tests/ -k analyze
python -m swebench_verified.analyze \
  --predictions bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl \
  --report      bench_reports/swebench-verified-crossrepo-50-20260806.json \
  --manifest    bench_reports/swebench-verified-crossrepo-50-selection-20260806.json \
  --trace-dir   swebench_work/traces-crossrepo-20-20260806 \
  --trace-dir   swebench_work/traces-crossrepo-50-20260806 \
  --harness-log-dir logs/run_evaluation/verified-crossrepo-50-utf8-20260806/dm-agent-deepseek \
  --prefix-count 20 --json <tmp>/s0.json --markdown <tmp>/s0.md
```

**产出**：`docs/research-log/44-offline-attribution.md`，含首次写入步号分布（尤其
resolved 组的 P90/P99）、解析失败形态分布、S3 规则的离线命中表。

---

### S1 — 把执行类工具路由进容器（治本项）

**证据**：§1.3、§1.4。执行类工具失败 214 次，两桶失败同一根因。
**成本**：5–7 天。**风险**：中高（容器生命周期、同步语义、成本）。

#### S1.0 开工前的成本闸门

镜像约 **3.9 GB / 题**。定向复跑 8 题需 ~31 GB（若镜像未缓存）。**先跑**：

```bash
docker system df
docker info --format "{{.ServerVersion}}"
```

磁盘余量不足 60 GB 时**停下来问用户**，不要自行 `docker system prune`——那会删掉
已归档实验复现所需的镜像。

#### S1.1 容器长驻

改 `swebench_verified/predict.py:262-284` 的 `materialize_workspace()`：

- 现在的容器（`dmagent-prep-<id>`）是 `docker create` + `docker cp` + 立即 `rm -f`。
  改为**保留一个长驻容器**，命名 `dmagent-exec-<instance_id 规范化>`，用
  `docker run -d --name <n> <image> sleep infinity`。
- **宿主工作区照旧拷贝**（`_copy_workspace_from_container` 一行不用改），
  `read_file` / `edit_file` / `git diff` 全部继续在宿主跑。
- 返回 `(workspace, container_name)`。

**生命周期（必须做对，否则会在用户机器上堆容器）**：

- 启动前先 `docker rm -f <name>` 清掉同名孤儿（`materialize_workspace` 已有这个模式，
  见 `predict.py:269`）；
- `predict_one` 用 **`try/finally`** 包住整个 agent 运行，`finally` 里无条件
  `docker rm -f`；
- 新增 `--keep-container` 调试开关，默认关，与现有 `--keep-workspace` 平行；
- `run.py` 批次开始前扫一次 `docker ps -a --filter name=dmagent-exec- -q` 并清理，
  应对上一轮被 Ctrl-C 打断留下的容器。

#### S1.2 三个工具的容器版

新建 `swebench_verified/container_tools.py`。三个 runner 都归结为一条：

```
docker exec -w /testbed <container> bash -lc "<激活命令> && <实际命令>"
```

| 工具 | 参数（`dm_agent/tools/__init__.py:114-132`，逐字不变） | 容器内命令 |
| --- | --- | --- |
| `run_shell` | `{"command": str}` | 原样 |
| `run_python` | `{"code": str}` 或 `{"path": str, "args": …}` | `code` 经 stdin 传入，**不要拼进命令行**（引号地狱） |
| `run_tests` | `{"test_path"?, "framework"?, "verbose"?}` | `python -m pytest <path>` |

**激活命令必须探测，不能假设。** SWE-bench 官方镜像通常是
`source /opt/miniconda3/bin/activate testbed`，但**以实际探测为准**：

```bash
docker exec <container> bash -lc "ls -d /opt/*/envs/* 2>/dev/null; which conda"
```

**探测失败时必须 fail fast，让整题记为 `harness_error`。绝不允许静默回落到宿主
执行**——那会把当前 37% 的失败率原样带回来，而且这次是隐藏的。这一条要有单元测试守住。

其他契约：

- 每次 exec 加超时（建议 300 s），超时返回可读 observation 而不是抛异常；
- stdout/stderr 合并、UTF-8 解码 `errors="replace"`（踩过坑 6：GBK 会把成功变成 error）；
- 输出交回内核由 `ObservationBounder` 截断，**容器版不要自己再截一遍**；
- 失败判定沿用 `dm_agent.core.observation.is_failure_observation`，不要另起一套。

#### S1.3 写后同步（这才是钩子的正确用途）

新建 `swebench_verified/container_sync.py`，一个 `AgentCapability`
（协议见 `dm_agent/core/capabilities.py:36-43`，模板照抄 `progress_guard.py`）：

- `after_tool_result`：`event.tool_name in WRITE_ACTIONS`
  （`dm_agent/core/guards.py:12`）且 `event.tool_succeeded` 时，
  把该文件 `docker cp <host_path> <container>:/testbed/<rel_path>`；
- 同步失败**不能静默**：追加进 observation 并记 trace `swebench_sync_failed`；
- 漂移检测按**决策 3** 实现（`git status --porcelain` → 告知 → 恢复）。

#### S1.4 finish 前的容器内 import 冒烟（原 P0-B，现在满血）

`before_finish` 钩子（`BeforeFinishEvent`，返回 `{"block": True, "reason": …}` 否决）：
对 patch 触及的每个 `.py` 推导模块路径，**在容器内** `python -c "import <mod>"`。

失败则否决 finish，把**容器里的真实报错**回灌给 agent。这正是 `astropy-13398` 那类
"改到整包 import 都挂了"的直接解药——而且因为在容器里跑，`np._core` 这种
"宿主有、容器没有"的差异**能真实复现**。

**防循环**：同一 run 内最多否决 2 次；第 3 次放行并记 trace
`swebench_import_smoke_exhausted`。守卫不能把 unresolved 变成 empty。

#### S1.5 安全断言（必须有测试守住）

1. 容器 `/testbed` 在 agent 启动前处于 `base_commit` 且工作树干净：
   `git rev-parse HEAD` == `base_commit` 且 `git status --porcelain` 为空。
   这等价于"官方 test_patch 尚未应用"，是本方案合法的前提。
2. 容器**不得**挂载任何宿主目录，尤其 `swebench_work/`（那里有 `instances.jsonl`，
   含 `FAIL_TO_PASS`）。实现上就是**不加任何 `-v`**，并写一条断言测试。
3. 沿用 `run.py` 的隔离原则：工作区父目录不含任何题目元数据。

> **关于泄漏的常见误解**：容器 `/testbed` 在 `base_commit` 上的内容与宿主工作区
> **逐字节相同**（宿主就是从它 `docker cp` 出来的）。因此容器路由**没有引入任何新的
> 可读信息**——agent 今天已经能读到的东西，明天还是那些。真正的护栏是断言 1 与 2。

#### S1 验收

**主指标（确定性计数器）**：执行类工具失败率。

```bash
# 复跑 §1.4 里执行类失败最集中的 8 道题，写新 output
python -m swebench_verified.run --limit 50 --max-steps 60 \
  --output swebench_work/preds-s1-exec8.jsonl \
  --trace-dir swebench_work/traces-s1-exec8
```

（题目子集的选取方式与 `preds-emptyfix-2` 先例一致；**必须写新 output，不得 `--resume`
到 50 题文件上**。）

**证伪判据**：若 `run_shell` + `run_python` + `run_tests` 合计失败率未从 **37.2%**
降到 **15% 以下**，S1 不成立，转入 §5 的回退方案。

**次要指标**：这 8 题的 resolved 变化。**单轮、8 题的 resolved 差异不构成证据**，
只作为方向性观察记录（见 §6）。

---

### S2 — 无写入预算守卫（针对 7 道空 patch）

**证据**：7 道 empty patch 题**60 步内 0 次文件写入**，占样本 14%。
其中 3 道（matplotlib-23476、seaborn-3069、sphinx-10614）**最后 20 步只有 1 个唯一
工具调用签名**——同一调用原地重复 20 次。

现有 `SWEProgressLoopGuard` 对 matplotlib-23476 已拦截 **33 次**重复搜索，
**拦完仍在循环**。问题不在"拦不住重复"，而在**拦截后没有强制转向**。

| instance | 60 步的调用分布 |
| --- | --- |
| matplotlib-23476 | `search_in_file`×49, `read_file`×10（0 次失败，纯循环） |
| seaborn-3069 | `read_file`×50, `search`×4, `search_symbol`×3 |
| sphinx-10614 | `read_file`×44, `search_in_file`×7 |
| django-14631 | `run_python`×28, `read_file`×11, `search`×7 |
| sphinx-9229 | `run_shell`×19, `read_file`×18, `search`×17（失败 14 次） |

> 注意后两道的画像里执行类工具占大头，**S1 可能独立改善它们**。因此 S2 的复跑
> 必须在 S1 之后进行，否则无法归因。

**设计**：新增 `swebench_verified/no_write_guard.py`（`AgentCapability`），三级递进：

| 阈值 | 触发条件 | 动作 | 钩子 |
| --- | --- | --- | --- |
| 软 N₁ | 连续 N₁ 步无 `WRITE_ACTIONS` | 追加系统提示：已探索 N 步无编辑，下一步应定位并修改文件 | `before_llm_request` |
| 硬 N₂ | 连续 N₂ 步无写入 | 只放行 `WRITE_ACTIONS` + `read_file`，其余带理由拦下 | `before_tool_call` |
| 兜底 N₃ | 连续 N₃ 步无写入 | 记 trace `swebench_no_write_forced`，注入"必须基于现有理解做出最佳猜测修改" | `before_llm_request` |

**N₁/N₂/N₃ 取自 S0.1 的首次写入步号分布**（软 = resolved 组 P90，硬 = P99 或 1.5×P90，
兜底 = 硬 + 10，全部取整）。三个阈值**可配置且必须写进 trace 与 metadata**，便于 ablation。
计数在 `on_run_start` 清零（照抄 `progress_guard.py:76-85` 的做法）。

新增诊断字段（`dm_diagnostics_version` 已在决策 6 升到 2）：
`dm_no_write_streak_max`、`dm_no_write_soft_hits`、`dm_no_write_hard_blocks`。

落点：`predict.py:416` 的 `capabilities=[...]` 追加。

**风险**：强制写入可能产出低质量 patch。但**空 patch 的期望收益是 0，劣质 patch 的
期望收益 ≥ 0**，方向上不亏。

**验证**：只复跑这 7 道题（S1 之后）。
**证伪判据**：若非空 patch 数 **< 4/7**，或新增的非空 patch 引发的 P2P 回归多于修复数，
方案不成立。

---

### S3 — patch 边界守卫（条件执行）

> **前置条件**：S0.3 的离线重放证明规则有效。**若 S0.3 判定无效，本阶段取消。**

**证据**：§1.5。

`before_finish` 钩子，三项检查：

| # | 规则 | 性质 | 动作 |
| ---: | --- | --- | --- |
| 1 | patch 含 `test_*.py` / `*_test.py` / `tests/` 路径 | **确定性** | **自动回退该文件后放行**（决策 5）；回退失败才否决 |
| 2 | 触及 > 3 个源文件 | 启发式 | 要求逐个说明必要性（软），**不硬拦** |
| 3 | 出现与题面关键词无交集的文件 | 启发式 | 给出警告，**不硬拦** |

落点：`swebench_verified/patch_scope_guard.py`。取 patch 复用
`predict.py:334-350` 的 `extract_patch()`，但**必须先过 `_assert_git_root()`**
（`predict.py:287-300` 的安全闸，绕过它 `git add -A` 会作用到本项目仓库上——实测差点中招）。

**防循环**：同一 run 内规则 2/3 最多提示 2 次。规则 1 是自动回退，不产生循环。

**验证**：S0.3 的离线重放即为验收，**不复跑**。

---

## 4. 明确不做的

| 不做 | 理由 |
| --- | --- |
| **加大 `--max-steps`** | §1.2 已实测证否：resolved 中位步数 8；跑满步数的 4 道 resolved 其正确 patch 均在上限前写成；7 道空 patch 题 60 步内 0 次写入，给 600 步也不会写。预期收益 0–2 题，成本翻倍，且 §1.5 显示更多步数 → 更大 patch → 更高 P2P 回归风险 |
| **P0-C（拦掉 `run_tests` + 声明环境不可用）** | S1 让这些工具真正可用，拦截逻辑随即作废。**纯止损、不提升能力**，且会与 S1 冲突 |
| **P4（shell 平台适配 / Unix 命令映射）** | S1 落地后命令都在 Linux 容器里跑，本项自动消解 |
| **重新引入 Reflexion / Critic / Self-Consistency / 熔断** | CLAUDE.md 明令禁止（devlog 33）。毕业标准依赖已冻结的评测，无法证伪。要复活只能写成外部扩展 |
| **自己写 verifier / 自己判分** | `swebench_verified/README.md:17-22`。自己判分的数字与 leaderboard 不可比，等于白跑 |
| **把改进做进 `dm_agent/` 内核** | 「内核最小化是本项目的宪法」。全部新增能力挂生命周期钩子或替换工具，装配在 `predict.py` |
| **一次性全量重跑 50 题** | 成本高（196 GB 镜像）且无法归因。全部用定向复跑验证 |
| **并行跑多题** | 现在是顺序执行。引入并发会同时带来容器命名冲突、磁盘峰值和不可复现的时序，收益只是墙钟时间 |

---

## 5. S1 失败时的回退

若 S1 的证伪判据被触发（执行类失败率降不到 15% 以下），**不要反复修补**。记录否定
结果，改用初稿的 P0-C：在 `PROMPT_TEMPLATE`（`predict.py:51-69`）里明确声明测试环境
不可用、不要尝试运行测试或安装依赖，并用 `before_tool_call` 拦掉 `run_tests` 与
`pip install`，直接返回可读理由。

成本半天，收益是省掉 26 次必然失败的 `run_tests` 和若干 `pip` 调用，把步数还给有用的
动作。**明确这是纯止损，不提升修复能力**——把它写进 devlog，不要包装成改进。

---

## 6. 判读纪律（四条，违反即实验作废）

1. **定向复跑的结果不得叠加回 42% 冒充新的 50 题总体分数。**
   README 对上一次 emptyfix 实验已写明这条边界。

2. **诊断字段缺失 = 未测量 ≠ 0。** 新增字段必须写新 output 验收，不能用 `--resume`
   静默保留旧记录（`swebench_verified/README.md:92-97`）。

3. **`P2P 全 0` 先查环境再下结论。** 打开 `test_output.txt`：若是 `cd $'/testbed\r'`
   之类则是宿主 I/O 故障（devlog 42 已修 CRLF + GBK）；若测试真跑了几十秒才失败，
   才是 agent 的真实回归。

4. **temperature 0 不等于确定性。** 同样的代码复跑同样的题，结果本来就会变。因此：
   - **主指标必须是确定性计数器**（工具失败率、非空 patch 数、拦截命中数），不是 resolved；
   - **≤ 8 题的单轮 resolved 差异不构成证据**，只作方向性观察记录；
   - 若某项改进观察到的效应量**不足证伪阈值的 2 倍**（例如失败率只降到 25%，
     而阈值是 15%），必须补一轮**关闭该能力**的对照复跑才能下结论。
     效应量远超阈值时（如 37% → 5%）可免对照，但要在 devlog 里写明这条豁免的依据。

---

## 7. 附录

### 7.1 跑满 60 步的 23 道题

| instance | 最后写入步 | 之后烧掉 | 尾20步唯一签名 | patch (B) | 结局 |
| --- | ---: | ---: | ---: | ---: | --- |
| django-14631 | 0 | 60 | 20 | 0 | EMPTY |
| matplotlib-14623 | 0 | 60 | 20 | 0 | EMPTY |
| matplotlib-23476 | 0 | 60 | **1** | 0 | EMPTY |
| seaborn-3069 | 0 | 60 | **1** | 0 | EMPTY |
| pylint-6386 | 0 | 60 | 18 | 0 | EMPTY |
| sphinx-10614 | 0 | 60 | **1** | 0 | EMPTY |
| sphinx-9229 | 0 | 60 | 20 | 0 | EMPTY |
| pytest-6202 | 4 | 56 | 10 | 395 | **RESOLVED** |
| astropy-13977 | 12 | 48 | 20 | 924 | unresolved |
| xarray-6744 | 20 | 40 | 19 | 1568 | **RESOLVED** |
| sphinx-7590 | 20 | 40 | 20 | 1765 | unresolved |
| django-12858 | 37 | 23 | 14 | 1589 | **RESOLVED** |
| requests-5414 | 38 | 22 | 19 | 1788 | unresolved |
| pytest-7236 | 42 | 18 | 19 | 1103 | **RESOLVED** |
| pytest-5787 | 47 | 13 | 19 | 11300 | unresolved |
| django-16950 | 51 | 9 | 17 | 615 | unresolved |
| matplotlib-25775 | 52 | 8 | 20 | 6605 | unresolved |
| requests-6028 | 53 | 7 | 19 | 1772 | unresolved |
| astropy-14995 | 54 | 6 | 20 | 2283 | unresolved |
| sklearn-25102 | 55 | 5 | 20 | 3245 | unresolved |
| sympy-13878 | 55 | 5 | 20 | 1186 | unresolved |
| astropy-13398 | 57 | 3 | 19 | 7709 | unresolved（P2P 0/68） |
| sympy-14248 | 58 | 2 | 20 | 2432 | unresolved |

### 7.2 复现本文数字

全部指标可从已归档文件离线重算，**不需要 Docker、不需要 API key、不需要联网**：

```
bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl   # dm_* 诊断字段
bench_reports/swebench-verified-crossrepo-50-20260806.json                # 官方 resolved/empty
bench_reports/swebench-verified-crossrepo-50-selection-20260806.json      # 选择契约
swebench_work/traces-crossrepo-20-20260806/                               # 前 20 题 trace
swebench_work/traces-crossrepo-50-20260806/                               # 新增 30 题 trace
logs/run_evaluation/verified-crossrepo-50-utf8-20260806/                  # 逐题 harness detail
```

"最后写入步号"与"尾 20 步唯一签名"两列由 S0.1 补进 `analyze.py`，之后本表可被
`--json` / `--markdown` 直接再生。

### 7.3 新增文件一览

| 文件 | 阶段 | 类型 |
| --- | --- | --- |
| `swebench_verified/container_tools.py` | S1 | 工具替换（非能力） |
| `swebench_verified/container_sync.py` | S1 | `AgentCapability` |
| `swebench_verified/import_smoke_guard.py` | S1 | `AgentCapability`（`before_finish`） |
| `swebench_verified/no_write_guard.py` | S2 | `AgentCapability` |
| `swebench_verified/patch_scope_guard.py` | S3 | `AgentCapability`（条件执行） |
| `docs/research-log/44-offline-attribution.md` | S0 | devlog |
| `docs/research-log/45-container-exec-routing.md` | S1 | devlog |

### 7.4 相关文档

- `docs/research-log/42-swebench-crossrepo-50.md` —— 本文基线运行的完整记录
- `docs/research-log/43-swebench-failure-analysis.md` —— 失败分层方法
- `docs/research-log/40-empty-patch-loops.md` —— 上一轮空 patch 治理与定向复跑先例
- `docs/research-log/33-scope-reduction.md` —— 为什么不能重新引入 Reflexion / Critic
- `docs/extensions.md` / `docs/lifecycle-events.md` —— 写钩子处理器前必读
- `swebench_verified/README.md` —— 评测子系统契约与六个已知坑
