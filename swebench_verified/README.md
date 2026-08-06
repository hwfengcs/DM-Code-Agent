# SWE-bench Verified 评测子系统

给 DM-Code-Agent 拿一个**能和公开数字对齐**的坐标。自带的 30 题 benchmark 衡量的是
过程纪律，但它是自建的、没有外部参照；SWE-bench Verified 的 resolved rate 有公开
leaderboard 可比。

## 为什么独立于 `dm_agent/`

CLAUDE.md 的约定：devlog 33 删掉的模块「要复活就写成外部扩展或独立子系统」。
这里选了独立子系统——

- 主项目 `pyproject.toml` / `uv.lock` **一行都不改**（devlog 33 删 `[swebench]` extra
  时，光 `datasets` 就拖来 26 个传递依赖、让 uv.lock 多 1393 行）；
- 数据集改用 HuggingFace 的 datasets-server JSON API，只用标准库 urllib；
- 官方 harness 装在**独立 venv**（`.swebench-venv/`）里，与主项目的依赖完全隔离。

## 为什么判分交给官方 harness

devlog 33 删掉 SWE-bench Lite 的直接原因是 Tier-1 verifier 在宿主环境跑测试、
resolved 0.0%，而 Tier-2（Docker）从未实现。这次不再自己写 verifier：
**我们只产出 predictions.jsonl，resolved 与否完全由官方代码判定**。
自己判分拿到的数字与 leaderboard 不可比，等于白跑。

## 环境准备（一次性）

需要 Docker Desktop 正在运行（`docker info` 能返回版本号即可）。

```bash
python -m venv .swebench-venv
.swebench-venv/Scripts/python.exe -m pip install swebench     # Windows
# Linux/macOS: .swebench-venv/bin/pip install swebench
```

Windows 额外需要 `_winshim/`：官方 harness `import resource`（Unix-only），
该目录提供一组 no-op 垫片，经 `PYTHONPATH` 注入，不污染 venv 的 site-packages。

## 跑一轮

### 先冻结选择

`run.py` 不再按数据集顺序取前 N。它先读取完整 Verified test 候选集，再生成稳定的跨仓库
选择序列：repo 之间 round-robin；每个 repo 内按 `<15 min fix`、`15 min - 1 hour`、
`1-4 hours`、`>4 hours`、`unknown` difficulty bucket round-robin；bucket 内用固定 selection
version 与 `instance_id` 的 SHA-256 排序。输入行顺序不会影响结果，`limit=N` 永远是
`limit=N+1` 的前缀。

先只看 20 题选择，不启动 Docker、不构造 LLM client、也不运行 Agent：

```bash
python -m swebench_verified.run --limit 20 --selection-only \
  --output swebench_work/preds-20.jsonl
```

命令只写 `swebench_work/preds-20.selection.json`，其中有有序 instance IDs、repo/difficulty
分布、完整候选集 fingerprint 与 selection signature，不含题面、`FAIL_TO_PASS` 或
`PASS_TO_PASS`。首次运行若还没有带完整性 metadata 的 cache，会通过 HuggingFace
datasets-server 拉取完整 test split；旧的 10 行 JSONL 没有完整性证明，会被识别为 partial
并替换。cache 仍位于 `swebench_work/`，不会复制进 Agent 工作区。

**第一步：预测**（在主 venv 里，需要 `.env` 的 API key）

```bash
python -m swebench_verified.run --limit 20 --max-steps 60 \
  --output swebench_work/preds-20.jsonl --trace-dir swebench_work/traces-20
```

每题会：拉官方评测镜像 → `docker cp` 出 `/testbed` 当工作区 → 跑 ReactAgent →
`git diff` 出 patch。断了用相同参数加 `--resume` 接着跑。续跑前会比较现有 manifest 与
当前 dataset/config/split、selection version、candidate fingerprint、limit 和 selection
signature；任何一项变化、manifest 缺失/损坏、prediction ID 越界或重复都会在 Docker/API
之前拒绝续跑。`harness_error` 仍会从旧输出移除并重试，已经真正跑过 Agent 的记录继续跳过。

如需显式指定 manifest 路径，使用 `--selection-manifest PATH`。

预测记录除官方要求的三列外，还带 `dm_status/failure`、`dm_patch_chars`、
`dm_duration_seconds`、`dm_difficulty`；正常完成 Agent run 时另带
`dm_diagnostics_version=1`、`dm_steps`、`dm_replans`、`dm_parse_errors/repairs`、
`dm_parse_error_context_omitted_count/chars`、`dm_truncations`、`dm_edit_guard_blocks`、
`dm_edit_noops`、`dm_repeat_search_blocks`、`dm_edit_state_revisits` 与
`dm_edit_cycle_blocks`。这些字段不参与官方判分，只用于区分“没修好”“探索/解析循环”和
“环境失败”，并给空 patch 治理提供不受 resolved 噪声影响的直接计数。后三个字段分别表示：

- 同一参数、同一文件内容版本上的精确重复搜索被拦截并回放缓存观察的次数；
- 实际写入后，文件内容回到本 run 已访问状态的次数；
- 可在执行前准确预测的 canonical 内容锚定 `edit_file` 二周期被拦截的次数。

编辑二周期的执行前预测只适用于 `old_string/new_string` 在当前内容中唯一命中的 canonical
内容锚定 `edit_file`。行号 `edit_file` 与 `create_file` 只在写后记录状态回访，不承诺提前
拦截；`run_shell` / `run_python` 即使改了文件，也不计为本守卫的状态转移。这个守卫只由
SWE-bench 的 `predict.py` 装配，不影响主 CLI 或 30 题 benchmark。

`dm_edit_noops` 严格只计 `old_string == new_string` 的 identity no-op，不代表所有“没有形成
patch”的调用；`dm_parse_error_context_omitted_chars` 只计未进入后续模型上下文的字符，审计
日志没有删除原文。正常完成一次 Agent run 时，诊断字段存在且为 0 才是实测零；旧
predictions、`agent_exception` 或 `harness_error` 没有 `dm_diagnostics_version` 或某个字段
时表示**未测量**，不能按真实 0 解读。验收新诊断字段时要写新 output，不能用 `--resume`
静默保留旧记录。

### 从 20 题扩到 50 题

改变 `--limit` 会改变 manifest，因此不能直接对 20 题输出加 `--limit 50 --resume`。安全的
扩容流程是显式创建一套 50 题契约，再利用前缀稳定性迁移已完成记录：

```powershell
python -m swebench_verified.run --limit 50 --selection-only `
  --output swebench_work/preds-50.jsonl
Copy-Item swebench_work/preds-20.jsonl swebench_work/preds-50.jsonl
python -m swebench_verified.run --limit 50 --max-steps 60 --resume `
  --output swebench_work/preds-50.jsonl --trace-dir swebench_work/traces-50
```

第三条命令会验证迁入的每个 ID 都属于 50 题选择；由于 20 题选择是 50 题选择的前缀，已完成
记录可以复用，剩余 30 题才进入预测。保留两套 output 与 manifest，报告即可追溯各自的样本
边界。执行前仍应先检查 Docker 磁盘占用，并由使用者决定是否承担真实运行成本。

**第二步：判分**（在 swebench venv 里）

```bash
PYTHONPATH=swebench_verified/_winshim \
  .swebench-venv/Scripts/python.exe -m swebench_verified.evaluate \
  --predictions swebench_work/preds.jsonl --run-id myrun --max-workers 4
```

产出 `dm-agent-<provider>.<run_id>.json`，逐题结果在 `logs/run_evaluation/<run_id>/`。
只想重看结论：`--summarize-only <report.json>`。空 patch 只进入汇总报告的
`empty_patch_ids`，不会生成该实例的 `patch.diff` / `eval.sh` / `test_output.txt` 目录。

## 成本

| 项 | 量级 |
| --- | --- |
| 镜像 | **约 3.9 GB / 题**，下载是主要瓶颈（50 题 ≈ 196 GB） |
| 预测 | 约 30 秒 – 19 分钟 / 题（DeepSeek，轨迹抖动很大） |
| 判分 | 约 20 秒 / 题（复用已有镜像） |

工作区默认建在系统临时目录，跑完即删（`--keep-workspace` 可保留，几百 MB / 题）。

## 结果

首轮 10 题（DeepSeek `deepseek-chat`、temperature 0、`--max-steps 60`，判分完全由
官方 swebench 4.1.0 完成）：**resolved 2 / 10 = 20%**，
存档在 `bench_reports/swebench-verified-10-20260805.json`。

6 道 unresolved 的分层比总数更有信息量——多数是"没修好"而不是"改坏了"：

| 实例 | FAIL_TO_PASS | PASS_TO_PASS | |
| --- | ---: | ---: | --- |
| astropy-12907 | 2/2 | 13/13 | **RESOLVED** |
| astropy-14309 | 1/1 | 141/141 | **RESOLVED**（4 步） |
| astropy-13977 | **12/20** | 318/322 | 修好一半 |
| astropy-13236 | 0/2 | **644/644** | 零回归 |
| astropy-14182 | 0/1 | **9/9** | 零回归 |
| astropy-13033 | 0/1 | 19/20 | |
| astropy-13398 | 0/4 | 63/68 | |
| astropy-13453 | 0/1 | **2/9** | 改坏了原行为 |

另有 2 题 60 步耗尽、产出空 patch：`astropy-13579` 被 identity no-op 与
`stale_read` 交替放大，`astropy-14096` 则是超长解析失败响应与重复读取形成二周期。
机制修复与三轮真实复跑见 [devlog 40](../docs/research-log/40-empty-patch-loops.md)。定向复跑的
直接指标已经达到 **empty patch 2 → 0**，官方 harness 结果如下：

| 实例 | patch | FAIL_TO_PASS | PASS_TO_PASS | 官方结论 |
| --- | ---: | ---: | ---: | --- |
| astropy-13579 | 1881 B | **1/1** | **40/40** | **RESOLVED** |
| astropy-14096 | 913 B | **0/1** | **426/426** | unresolved，零 P2P 回归 |

归档报告 `bench_reports/swebench-emptyfix-2-20260806.json` 为 submitted 2、empty patch 0、
resolved 1/2、harness error 0。14096 虽不再为空，仍跑满 60 步；44 次 `run_python` 中
有 **35 次参数逐字相同**，是尚未治理的残余固定点。13579 的预测早于三个新进度环字段，
字段缺失表示未测量，不是 0。

这只是针对原两道空 patch 题的定向复跑，不能把 1/2 直接叠加到首轮 2/10，伪装成新的
10 题总体分数。结果来自已实际运行的机械修复轮与纯事件守卫轮；随后对未触发的编辑二周期
分支做了确定性契约收紧，没有再消耗模型调用，因此 1/2 也不冒充收紧后源码树的新端到端
分数。细节与适用边界见 devlog 40。

> 这 10 题是旧版本按数据集顺序取前 N 的历史结果，**全部来自 astropy 单一仓库**，
> 不构成对 SWE-bench Verified 整体的估计。新的跨仓库选择契约只影响后续运行，不改写
> 已归档实验的样本定义或分数。

### 跨仓库 20 → 50 真实结果

使用 selection manifest v1、DeepSeek `deepseek-chat`、temperature 0、max steps 60：

| 范围 | resolved | completed | empty patch | error |
| --- | ---: | ---: | ---: | ---: |
| 前缀 1–20 | **11/20 = 55%** | 18 | 2 | 0 |
| 新增 21–50 | **10/30 = 33.3%** | 25 | 5 | 0 |
| 总体 1–50 | **21/50 = 42%** | 43 | 7 | 0 |

20 题是 50 题的严格嵌套前缀，50 文件只新增运行后 30 题，因此两行不是独立复验。
20/50 分别覆盖 12 个仓库；50 题 difficulty 为 easy 21、medium 18、hard 8、very hard 3。
完整配置、失败分层、过程计数和 Windows host 修复见 [devlog 42](../docs/research-log/42-swebench-crossrepo-50.md)。

## 六个踩过的坑

都是「在 Windows 上跑 Linux 仓库」引出的，改错任何一个都会让分数无效：

1. **题目数据泄漏**。工作区一开始放在 `swebench_work/workspaces/<id>`，agent 用
   `run_shell` 爬到父目录读走了 `swebench_work/instances.jsonl`——里面有
   `FAIL_TO_PASS`，等于把隐藏测试名喂给被测对象。现在工作区放系统临时目录，
   与题目数据物理隔离，prompt 里也加了「只在当前目录工作」。

2. **工作区一建好就是脏的**。镜像在 Linux 上构建，`docker cp` 到 Windows 后
   15 个文件从 100755 掉成 100644，加上全局 `core.autocrlf=true`，一个还没被
   agent 碰过的工作区 `git diff` 就非空。仓库级设 `core.fileMode=false` +
   `core.autocrlf=false` 解决。

3. **改一行产出整文件 diff**。`Path.write_text` 默认的 `newline=None` 会把 `\n`
   按平台改写成 `\r\n`，于是编辑一个 LF 文件会把整份文件转成 CRLF：实测 patch
   从 504 B 涨到 20595 B、`+317/-317`。这个是主项目 `tools/file_tools.py` 的缺陷，
   已一并修掉（本地 30 题 benchmark 看不到它，因为那些工作区文件都是新建的、
   行尾自始至终一致）。

4. **官方 harness 自己也中了同一个行尾陷阱，而且最阴险**。
   `run_evaluation.py:199` 用 `write_text` 写 `/eval.sh` 再 copy 进 Linux 容器执行，
   Windows 上写出 CRLF，容器里的 bash 把 `\r` 当成命令的一部分：

   ```
   + cd $'/testbed\r'
   /eval.sh: line 7: cd: $'/testbed\r': No such file or directory
   + git $'status\r'
   git: 'status' is not a git command.
   ```

   **每条命令都失败、测试一个都没跑**，而报告里的表现是 **PASS_TO_PASS 全 0**——
   看着像 agent 把整个模块改坏了。10 题实测全中，`resolved 0/10` 完全是这个 bug 的
   产物；`evaluate.py:force_lf_writes()` 修补后，同一批 predictions 重判
   **resolved 0 → 2**。

   > 判读时记住：**`P2P 全 0` 是环境故障的指纹，不是能力信号**。agent 改一行不可能
   > 让 322 个原本通过的测试全挂。

5. **Windows 不能直接 materialize 镜像里的 symlink**。Django 镜像的 `docker cp`
   会因创建链接权限失败。现在从 stdout 接收 tar 并受控解包：Windows 写 Git link-target
   文本并设置 `core.symlinks=false`，Linux/macOS 保留原生 symlink 与 mode；路径穿越、
   重复目标、Windows 保留名和大小写冲突会被拒绝。

6. **GBK 会在测试跑完后把成功判分变成 harness error**。官方代码存在未指定 encoding
   的文本写入，输出含非 GBK 字符时抛 `UnicodeEncodeError`。`force_lf_writes()` 现在同时
   显式使用 UTF-8；最终 20/50 报告均为 `error=0`，早期受编码故障影响的报告不作能力数字。

另有一道安全闸 `_assert_git_root`：工作区必须自己就是 git 仓库根，否则拒绝执行
`git add -A`——否则 git 会向上查找，作用到本项目的仓库上（实测差点中招）。

`--resume` 只跳过真正跑过 agent 的题；`harness_error`（daemon 挂了、镜像拉不下来）
会被重试。早期版本把环境失败也当"已完成"，重跑会静默跳过全部失败题。
