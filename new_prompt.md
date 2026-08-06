# DM-Code-Agent 下一窗口交接 Prompt

> 将本文件从 `---` 开始的内容完整交给下一个 AI 窗口。它描述的是 2026-08-07 的仓库状态；
> 如果实际仓库、用户新指令或本文件不一致，以实际仓库和用户最新指令为准。

---

你正在接手 `C:\Users\ECNU\Desktop\DM\DM-Code-Agent`。默认中文交流，深度工作后再汇报。

## 0. 开始前的硬性步骤

完整阅读：

1. `AGENTS.md` 与 `CLAUDE.md`（若存在）；
2. `README.md`、`README_EN.md`；
3. `docs/recent-progress.md`、`docs/project-status.md`；
4. `swebench_verified/README.md`；
5. `docs/research-log/42-swebench-crossrepo-50.md`。

然后运行：

```powershell
git status --short --branch
git log -5 --oneline
```

不要猜测状态。不要使用 `git reset --hard` 或批量删除。除非用户明确要求，不要 push。

## 1. 项目定位与不可破坏的约束

DM-Code-Agent 是本地优先、可审计的 Python Code Agent：ReAct + Planner + Replan，
append-only session/trace，工具调用、失败阶段、恢复与验证缺口都应可诊断和复放。

- 原始 session/trace 永不覆盖、删除；折叠只能追加派生记录。
- 默认测试、确定性 eval、benchmark manifest 检查不得需要 API key、网络或 Docker。
- 先问“这必须进 kernel 吗？”；SWE 专用行为留在 `swebench_verified/` 或扩展层，
  不给 `ReactAgent` 增加 SWE 分支。
- 不重新引入已移除的 Reflexion、Critic、Self-Consistency、通用熔断、记忆卫生、
  LLM 摘要压缩等默认模块。
- 新代码保持小而显式；不新增依赖，除非确有必要并同步 `uv.lock`。
- 任何真实模型、Docker 镜像、HuggingFace/GitHub 下载或付费 API 调用前，先向用户说明
  成本、耗时和命令；本窗口默认只做离线实现与验证。
- 修改 benchmark 行为时同步测试和文档；不把未实际运行的分数写成结果。

## 2. 当前已被真实证据支持的状态

当前归档提交：`4b966c4 docs: document recent experiments and verified runs`。

最近代码提交：

- `74f96ce fix(swebench): harden real 50-task evaluation`
- `16fd255 feat(swebench): add deterministic selection manifests`
- `d59e2d5 fix: eliminate SWE-bench empty-patch loops`

离线验证基线（本次接力前已实跑）：`529 passed, 1 skipped`；ruff、black、mypy、
compileall、确定性 eval、maintenance manifest listing、全量 pre-commit 均通过。再次验证时
以实际输出为准，不要机械复制这个数字。

自带 benchmark 是 30 题（coding 15 + maintenance 15），13 题只是历史 baseline。
repeat-3 的经验噪声底约 ±5 题；30 题单题翻转 ±3.3 个百分点只是分辨率，不能当作噪声。

SWE-bench Verified 使用官方 `swebench==4.1.0` harness：

- 20 题：11/20 resolved（55%），empty patch 2，error 0；
- 50 题：21/50 resolved（42%），completed 43，empty patch 7，error 0；
- 20 题是 50 题的严格前缀，50 题复用前 20 题 predictions，只新增运行 30 题；
- 这是本地确定性 50 题子集，不是完整 500 题分数，也不是 leaderboard 提交。

长期证据三件套在 `bench_reports/`（该目录通常被 ignore，不能擅自声称已入 Git）：

```text
swebench-verified-crossrepo-{20,50}-20260806.json
swebench-verified-crossrepo-{20,50}-predictions-20260806.jsonl
swebench-verified-crossrepo-{20,50}-selection-20260806.json
```

本机可能还有 `swebench_work/instances.jsonl`、predictions、selection manifest 与
`logs/run_evaluation/`；它们可能包含敏感或隐藏测试相关数据，先检查权限和 gitignore。
50 题 trace 通常分在 `swebench_work/traces-crossrepo-20-20260806` 与
`swebench_work/traces-crossrepo-50-20260806` 两个目录，不能只读取后一个。

## 3. 本窗口主任务：离线 SWE 失败分析器

这是当前最高杠杆的下一步：真实 50 题已经有结果，但失败原因仍需要手工把 prediction、
Agent trace 与官方 harness report 对齐。实现一个小而可复用的离线分析器，建议落在
`swebench_verified/analyze.py`，必要的薄 CLI 接在现有 `swebench_verified` 命令体系中；
不要改 kernel，不要自己实现 SWE verifier，不要重新运行 20/50 题。

### 输入契约

支持显式路径参数：

- predictions JSONL（至少读取 `instance_id`、`model_patch`、`dm_*` 诊断字段）；
- 官方 harness report JSON（读取 submitted/completed/resolved/unresolved/empty/error IDs）；
- 可重复传入的 trace 根目录（每个 instance 一个 append-only JSONL）；
- 可选官方逐题 harness detail 目录（empty patch 没有 detail 是正常情况）；
- 可选 selection manifest（检查样本边界和 repo/difficulty 元数据）。

缺失 trace、缺失诊断字段、旧格式 prediction 或 report 中不存在的 instance 必须明确标记
为 `unknown`/`missing`，不能静默当成 0，也不能让一条坏 trace 使全批失败。显式传入但不存在
的目录应报错；目录存在但少实例时继续分析并输出 warning。

核心输入要 fail fast 校验：predictions 的 ID 不重复且顺序等于 manifest；report 的
`submitted_ids` 等于 manifest；resolved/unresolved/empty/error 四类 ID 互斥且并集完整，
计数与数组长度一致。不要使用 report 的 `incomplete_ids` 判断本批缺失——它包含完整 500
题 split 中未提交的 450 题。trace 以 `runtime.payload.instance_id` 为权威映射，文件名只作
旧 trace 的 warning fallback；同一 ID 出现在多个目录必须拒绝。

### 输出契约

提供机器可读 JSON 和人类可读 Markdown/console 输出。逐题至少记录：

- `instance_id`、repo、difficulty（若 manifest 可得）；
- 官方结论：resolved / unresolved / empty_patch / harness_error / incomplete；
- patch 是否为空、patch 字符数；
- Agent 状态、失败信息、steps、duration、replans；
- parse errors/repairs、truncations、edit guard blocks/noops、repeat-search blocks、
  edit-state revisits、edit-cycle blocks；
- trace 是否存在、是否出现 max-steps、重复工具签名、验证缺口；
- direct write tool calls（`edit_file/create_file`）与最终 patch 为空只能作为 advisory，
  不能将其命名为已证明的 no-edit/root cause；`run_shell/run_python` 也可能修改文件；
- 可多选失败标签：`empty_patch`、`no_edit`、`max_steps`、`parse_error`、
  `guard_block`、`f2p_unresolved`、`p2p_regression`、`harness_error`、`unknown`。

汇总至少按总体、repo、difficulty、官方结论和失败标签聚合计数，并保留分母。结果轴必须分离：

1. 官方结果轴：resolved / unresolved / empty / harness error；
2. harness detail 轴：F2P-only、F2P+P2P、P2P-only、patch apply failure、detail unavailable；
3. Agent/trace 轴：success/max-steps/exception、patch chars、parse、guard、重复调用等。

明确区分“Agent 主循环成功结束”与“官方 harness resolved”，不能把 `dm_status=success`、
非空 patch、F2P 通过或 max-steps 当作修复成功或单一根因标签。

### 安全与可复现性

- 只读输入，禁止修改 prediction、trace、report、selection 或仓库源码。
- 默认不需要网络、Docker、API key；路径错误和坏 JSON 给出清楚错误。
- JSON 字段、Markdown 表格、分类标签和实例顺序必须确定；不要用 Python `hash()`。
- 不把题面、`FAIL_TO_PASS`、`PASS_TO_PASS` 或 secrets 写入输出。
- 同一 instance 可保留多个标签并定义稳定顺序，不用单一分类掩盖信息。
- 对缺失值使用 `null`/明确状态，不把“未测量”伪装成真实 0。

### 测试验收

新增离线测试（建议 `tests/test_swebench_analysis.py`），至少覆盖：

1. synthetic predictions/report/trace 的最小完整样例；
2. 官方 report 字段到逐题结论的映射，且 `incomplete_ids` 不污染本批统计；
3. 空 patch、max-steps、parse error、guard block、F2P-only、F2P+P2P、P2P-only、harness error；
4. 缺失 trace、旧字段、重复 ID、坏 JSON、未知 instance 的可解释处理；
5. 相同输入两次输出逐字段一致，repo/difficulty 聚合分母正确；
6. 默认 pytest 不触网、不启动 Docker、不构造 LLM client。

离线回归可直接用已归档三件套断言：all=21 resolved/22 unresolved/7 empty/0 error，
prefix=11/7/2/0，remainder=10/15/5/0；若本机 detail/trace 齐全，额外核对 all nonempty=43、
success/max-steps=27/23、steps=1757、parse errors=117、repeat-search blocks=49。

建议命令形态（以现有 CLI 风格为准，不为形式创建大框架）：

```powershell
python -m swebench_verified.analyze `
  --predictions bench_reports/swebench-verified-crossrepo-50-predictions-20260806.jsonl `
  --report bench_reports/swebench-verified-crossrepo-50-20260806.json `
  --manifest bench_reports/swebench-verified-crossrepo-50-selection-20260806.json `
  --trace-dir swebench_work/traces-crossrepo-20-20260806 `
  --trace-dir swebench_work/traces-crossrepo-50-20260806 `
  --harness-log-dir logs/run_evaluation/verified-crossrepo-50-utf8-20260806/dm-agent-deepseek `
  --prefix-count 20 `
  --json $env:TEMP\swebench-analysis.json `
  --markdown $env:TEMP\swebench-analysis.md
```

没有传入 trace/detail 时，分析器仍应完成三件套级别分析并报告 unmeasured 数；传入的目录
不存在则 fail fast。`--prefix-count 20` 应同时给出 all、prefix_1_20、remainder_21_50，
且可加计数逐字段一致。

## 4. 文档与交付要求

- 更新 `swebench_verified/README.md`，说明输入、分类口径、离线命令和缺失数据行为。
- 新增研究日志 43，记录三轴 taxonomy、输入缺失语义、为何合并“外部 resolved”与“内部过程指标”，
  并写清楚本任务没有真实重跑。
- 若 README 或 `docs/project-status.md` 增加数字，必须引用已归档 report；不能声称
  分析器提高了 resolved rate。
- 完成功能时不要顺手覆盖本交接文档； staged diff 必须逐文件审查。

## 5. 完成前验证

至少运行：

```powershell
python -m compileall dm_agent main.py tests swebench_verified
python -m pytest
python -m ruff check .
python -m black --check .
python -m mypy dm_agent
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
uv run --frozen --extra dev pre-commit run --all-files
```

失败时停止并重新规划，不要带病提交。完成后用一个聚焦的 Conventional Commit；不要 push。

交付必须说明：改了哪些文件、输入/输出契约、测试结果、是否联网/调用 Docker/API、commit
hash，以及仍未解决的下一步。

## 6. 后续优先级（不要与主任务混做）

1. 用分析器离线生成 20/50 题 failure matrix，确认分类覆盖率和 unknown 数量；
2. 从最稳定的失败标签设计一个小型、可证伪的 guard，先用 synthetic/replay 验证；
3. 冻结 manifest 后做跨仓库 sentinel repeat-3，先向用户报告成本；
4. 扩充 maintenance benchmark 的文档一致性、CI 配置、多文件重构和多轮修复任务；
5. 把 devlog 36–42 整理成公开技术复盘与 5 分钟演示。
