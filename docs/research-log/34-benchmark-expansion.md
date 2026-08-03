# 34 · 把评测集从 13 题扩到 30 题

- 日期：2026-08-03
- 相关：[09](09-maintenance-realism.md) [33](33-scope-reduction.md)

## 为什么

devlog 33 把记分牌扶正之后，13 题的统计噪声成了最刺眼的问题：**一题翻转 = ±7.7 个
百分点**。这个粒度下，除非一次改动翻转三四题，否则分数变化根本无法与重跑抖动区分。
实测证据就在手边——同一模型、同样 6 道 coding 题，两次运行分别是 3/6 和 4/6。

30 题把噪声底降到 **±3.3 个百分点**，这是扩题的主要收益，不是"题多显得厉害"。

## 设计依据来自 baseline 的失败模式

不是随便找 17 个题目凑数。13 题 baseline 暴露的三个失败模式直接决定了新��的形态：

| baseline 失败模式 | 占比 | 新题如何回应 |
| --- | --- | --- |
| 改了不该改的文件（全是去改测试） | 3/8 | 新增 maintenance 题**全部**带 `allowed_changed_files` |
| 步数耗尽 | 4/8 | 新题 `max_steps` 按实际复杂度给到 14–18，不故意卡死 |
| 输出格式崩坏 | 1/8 | 与题目无关，属模型侧问题 |

同时补了原任务集的能力盲区。新增 coding 9 题：`parse_duration`（解析）、
`merge_intervals`（区间边界）、`retry_backoff_schedule`（退避）、`csv_row_parser`
（带引号转义的解析）、`paginate_cursor`（游标分页）、`semver_compare`（版本序）、
`flatten_config`（递归）、`rate_limiter_window`（滑窗状态机）、`safe_int_parse`
（严格类型强制）。新增 maintenance 8 题：`billing_period_boundary`（日期月末夹取）、
`sql_where_builder`（参数化，防注入）、`idempotent_job_runner`（幂等 + 失败不缓存）、
`sort_stability_regression`（稳定排序 + 要求补回归测试）、`filename_sanitizer`
（跨平台文件名 + Windows 保留设备名）、`error_propagation_contract`（跨文件异常翻译
契约）、`settings_env_precedence`（跨文件配置优先级 + 按默认值类型强制）、
`log_redaction`（递归脱敏 + 不可变输入）。

设计上刻意让每题的隐藏测试都卡在**可见测试不覆盖的那一类边界**上——例如
`merge_intervals` 的可见测试只有重叠区间，隐藏测试考的是"相接"区间 `(1,3)+(3,5)`；
`safe_int_parse` 的隐藏测试考 `bool` 是不是应该被当成 int（不应该）。

## 三条不变量

前两条已经写成单测（`tests/test_coding_benchmarks.py`），对全部 30 题统一断言：

1. **初始工作区下隐藏测试必须失败。** 否则这题白送分。
2. **隐藏测试文件不得出现在 `allowed_changed_files` 里。** 否则等于允许 agent 改
   判分标准——考虑到 baseline 里三题都试图改测试，这条不是假想威胁。

第三条无法在无 key 的单测里对全部题目断言（需要 30 份参考解），改为加题时手工验证：

3. **题目必须可解。** 本次为 17 道新题各写了一份参考实现，逐一确认隐藏测试全绿。
   一道无解的题会让 agent 永远丢分，且极难从报告里看出是题目的错。

可见测试初始是过是挂**不设约束**：挂的给 agent 明确起点，过的逼它从任务描述推断边界。
原 13 题里 7 过 6 挂，新题保持这个混合。

## 连锁影响

- `suite_signature` 必然改变 ⇒ CI 的 manifest guard 会 fail。这是守卫按设计工作，
  处理方式是重新生成 `bench_reports/manifest-baseline-*.json`（本次已做）。
- **旧 baseline 作废**。`bench_reports/baseline-20260803.json` 是 13 题的分数，
  与 30 题不可比。`dm-agent-score-diff` 会因签名不同直接拒绝比较并 exit 2——
  已实测确认，这正是那个检查存在的意义。扩题后必须重跑 baseline。

## Open questions / next bets

1. 30 题下 `--repeat 2` 是否值得？能把单次抖动摊平，代价是跑一次翻倍。
2. maintenance 在 13 题 baseline 上只有 1/7。新增 8 题后如果整体仍然极低，
   说明瓶颈在"多文件 + 约束遵守"而非题目难度，那该动的是 prompt 或加个
   `before_tool_call` 守卫拦下对 `tests/` 的写入，而不是继续加题。
3. 题目难度分布目前靠人工判断。跑过一轮真实 baseline 后可以按通过率分档，
   把"没有任何模型能过"和"所有模型都能过"的题挑出来复核——两者都不提供区分度。
