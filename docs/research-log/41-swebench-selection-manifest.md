# 41 · SWE-bench 跨仓库分层选择与 selection manifest

- 日期：2026-08-06
- 相关：[40](40-empty-patch-loops.md)

## TL;DR

首轮 Verified 直接取数据集前 10 条，结果全部来自 astropy。问题不在随机种子，而在候选集
本身被旧 10 行 partial cache 截断。本轮把“完整候选集”和“选择前缀”分别冻结：cache 只有
在 sidecar 明确记录完整 split、行数与全内容 fingerprint 时才可信；选择使用 repo 外层
round-robin、repo 内 difficulty round-robin、bucket 内固定版本 SHA-256 排序。每次运行写
不含题面和隐藏测试的 manifest，`--resume` 在 Docker/API 之前校验该契约。

本轮只完成代码、synthetic 测试和离线验证，没有运行新的真实预测或官方 harness，因此没有
新的 resolved rate。

## Context

旧 `fetch_instances(limit)` 有两个耦合缺陷：网络只拉前 N 条；只要 JSONL 行数不少于 limit，
就把 cache 当成完整候选集。已有 10 行 cache 恰好全部是 astropy，因此即使在这 10 行上增加
“分层抽样”，外观会改变，外部有效性不会改变。

完整候选集 cache 含 `problem_statement`、`FAIL_TO_PASS` 和 `PASS_TO_PASS`，所以仍留在
`swebench_work/`，不进入系统临时目录中的 Agent checkout。新增 sidecar 只记录摘要和完整性
元数据；没有 sidecar 的 legacy JSONL 一律按 partial 处理，不猜“Verified 当前应有 500 行”。

## Selection contract

算法先构造一个与 limit 无关的全局有序序列，再截取前缀：

1. 按 repo 原字符串稳定分组和排序。
2. repo 内把 difficulty 规范为 `<15 min fix`、`15 min - 1 hour`、`1-4 hours`、
   `>4 hours`、`unknown` 五个 bucket，并按该顺序 round-robin。
3. bucket 内按 `SHA-256(selection_version + instance_id)` 排序，以 `instance_id` 作最终平局键。
4. 最外层对 repo round-robin，直到候选耗尽；`limit` 只对完整序列切片。

因此同一 selection version 下，输入 shuffle 不改变结果，`limit=N` 是 `limit=N+1` 的严格
前缀。repo 字典序会固定承担“不满一轮”的余数，这是确定性与简单可解释性的取舍；当 repo
尚未耗尽时，每轮最多各取一道，分配差不超过 1。

没有采用加权随机抽样：固定 seed 仍需要冻结 PRNG 实现和调用顺序，而且扩容时通常不具备
prefix stability。也没有按 repo 配额后分别截断，因为配额会随 limit 变化，20 题选择未必
是 50 题选择的前缀。

## Manifest and resume guard

manifest 只从白名单标量重建，记录 schema、dataset/config/split、selection strategy/version、
候选数、候选 fingerprint、requested limit、ordered IDs、repo/difficulty counts 和 selection
signature。candidate fingerprint 只哈希影响选择的 `instance_id/repo/normalized difficulty`；
cache sidecar 的 fingerprint 则覆盖缓存的全部字段，两者职责不同。

`--resume` 的兼容策略是严格拒绝猜测：output 已存在但 manifest 缺失/损坏，选择字段或
signature 不同，prediction ID 不在当前选择内，或同一 ID 重复，均在 output 改写、Docker
preflight 与 Agent 运行前退出。相同契约下，`harness_error` 仍会被清掉并重试。

20 -> 50 扩容不允许静默改变同一 output 的样本定义。先生成 50 题 manifest，再显式把 20 题
prediction 复制到新的 50 题 output；prefix stability 保证这些 ID 属于新选择，resume guard
负责逐条验证，然后只运行剩余 30 题。

## Deterministic evidence

synthetic fixture 包含 3 个 repo、9 道题和全部五类 difficulty。前 6 道的 repo 分布固定为
`2/2/2`；difficulty 分布固定为 `<15 min fix: 2`、`15 min - 1 hour: 2`、
`1-4 hours: 1`、`>4 hours: 1`。这组前 6 道的 selection signature 固定为
`c1f168dbab420843e690a6f66375618a57b1b164fde83bb3b4441798e7981991`。测试同时逐字段
比较原输入与固定 seed shuffle 后的 manifest，并检查从 0 到候选总数的每个 limit 都是完整
序列前缀。

离线回归还覆盖：三页 synthetic 分页、legacy partial cache 强制刷新、完整 cache 零网络复用、
unknown difficulty fallback、manifest 不含题面/隐藏字段、selection-only 不调用 Docker 或
prediction、resume mismatch 不修改旧 output，以及 `harness_error` 仍只重试对应实例。

## Not measured

本轮没有联网拉取 HuggingFace 数据，没有调用 Docker，没有使用 API key，也没有运行真实
20/50 题预测或官方 harness。这里不声明 repo 实际覆盖数、磁盘占用、耗时或 resolved 提升。
下一步应由使用者先用 selection-only 检查真实 manifest，再决定是否承担跨仓库 20 题运行
成本；确认流程后，才显式扩到 50 题。

## Open questions / next bets

- 用真实完整 cache 跑 selection-only，检查 20/50 题的 repo 与 difficulty 实际分布。
- 在用户确认 Docker、API、时间和磁盘成本后，先执行 20 题流程验证，再冻结 50 题 manifest。
- 下一阶段单独实现离线失败分析器，不与本次选择契约混在同一提交。
