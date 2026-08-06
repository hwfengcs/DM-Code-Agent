# 40 · 空 patch 的两种死循环：编辑新鲜度与解析失败上下文

- 日期：2026-08-06
- 相关：[23](23-observation-truncation-and-token-budget.md)
  [38](38-edit-file-precision.md) [39](39-observation-failure-classification.md)

## 一句话

SWE-bench 首轮两个空 patch 不是同一种失败：`astropy-13579` 是 identity no-op 被当成
写入后触发 `stale_read`，`astropy-14096` 是超长 malformed 响应留在近期窗口，和同一段
`read_file` 形成确定性二周期。本轮按来源分别修：内容锚定编辑免除自身写入造成的 stale，
identity no-op 不落盘、不备份，也不推进写台账或 planner 进度；解析失败原文继续
append-only 留档，但后续上下文只放显式记录的短占位。真实复跑又依次暴露出重复搜索和
编辑撤销二周期，因此只在 `swebench_verified/` 装配了确定性的事件守卫。最终两题的空 patch
从 **2 → 0**：`astropy-13579` 产出 1881 B patch 并被官方 harness 判为 resolved；
`astropy-14096` 产出 913 B patch，但 FAIL_TO_PASS 仍未通过。**打破循环不等于修好题目。**

## 诊断一：`astropy-13579` 不是“反复改回原样”

这题 60 步耗尽，最终 patch 为空。22 次 `edit_file` 全部走 `old_string/new_string` 内容锚定
模式，其中 11 次执行、11 次被守卫拦下。进一步对参数逐字比较后发现：**22 次的
`old_string == new_string` 全都成立**。所谓 `1146 -> 1146 字符` 不是长度碰巧相同，而是
模型把原文原样交回工具。

旧链路把 runner 正常返回等同于“发生写入”：

```
identity edit（文件未变）
  → 登记 write generation
  → 下一次 edit_file 命中 stale_read
  → 重读
  → 再次 identity edit
```

因此守卫是放大器，但不是唯一根因。仅关闭守卫会让 22 次无效编辑更快通过，也会丢掉它
已经挡住过的真实行号漂移。

## 诊断二：`astropy-14096` 不是定位不到文件

第 2 步已经读到正确的 `sky_coordinate.py` 与目标 `__getattr__`。60 步构成为：

| 动作 | 次数 |
| --- | ---: |
| `read_file` | 29 |
| 解析失败 | 27 |
| 搜索 | 3 |
| 执行 | 1 |
| `edit_file` | **0** |

step 9 以后形成严格二周期：一个 31,213 字符的无效响应，与完全相同的
`read_file(869–910)` 交替出现。23 个巨型失败响应哈希完全相同，解析失败响应占总响应字符
**94.8%**。48 次折叠中 47 次折叠后仍超过 24k token 预算，因为近期窗口按设计保留最近
消息，巨型 malformed assistant 原文一直没有离开有效上下文。

这说明这里的病根不是搜索能力，而是“审计原文”和“下一轮模型输入”被错误地当成同一份
数据。原始响应必须保留，但不必反复送回模型。

## 设计：分开修，不加通用熔断器

### 1. `stale_read` 按编辑模式解释

状态仍由 run 内动作台账确定，不引入 mtime/hash：

| 台账状态 | 内容锚定编辑 | 行号编辑 |
| --- | --- | --- |
| 从未读取 | 拦截 `never_read` | 拦截 `never_read` |
| 已读取、未写入 | 允许 | 允许 |
| 自己写入后未重读 | **允许** | 拦截 `stale_read` |

内容锚定模式每次执行都会读取当前文件，并要求 `old_string` 在当前内容中唯一精确命中；零
命中或多处命中时不写文件。它不依赖旧行号，因此自己的上一次写入不会让锚点“过期”。
台账仍保持 stale，后续若切回行号模式，守卫继续要求重读。

### 2. identity no-op 是明确的未写入结果

`old_string == new_string` 时，`edit_file` 在落盘前返回“未改动”，不调用原子写；调用链
也跳过写前备份，并把结构化 `no_change` 带回主循环。因此它不推进写台账，也不会把 planner
中同名的编辑步骤误标为完成。run metadata 增加 `edit_noop_count`，trace 增加
`edit_noop`，让“模型尝试编辑了多少次”和“实际产生修改多少次”不再混为一谈。
这里的 `no_change` 表示“预期编辑效果未发生、没有计划进展”，不是泛指工具没有持久化副作用；
成功的读取工具已经完成预期效果，不应仅因只读而设置该信号。

### 3. malformed 原文与上下文派生视图分离

解析失败时仍追加原始 assistant `message`；完整 checkpoint 或显式 `--trace-llm-io` 仍可
审计全文。容错解析已经穷尽仍失败的响应，无论长短，后续 `conversation_history` 都改用短
占位，metadata 记录省略次数与字符数。这样规则由“解析结果是否可信”决定，不引入另一个
任意字符阈值。

紧随其后的 `parse_error` 事件显式写入当时实际使用的 `context_replacement`，读侧
`rebuild_context` 只对带该字段的新事件替换。旧 trace 没有此字段——旧版本当时确实把
malformed 原文留在上下文里，所以必须保持旧语义，不能事后“修漂亮”。

### 4. SWE-bench 预测记录暴露直接计数

新增 `dm_diagnostics_version=1`，以及解析失败、上下文省略、guard block 与 identity no-op
字段。后续进度环守卫又增加三个直接计数：

- `dm_repeat_search_blocks`：同一参数、同一目标文件内容版本上的精确重复搜索被拦截并回放
  缓存观察的次数；
- `dm_edit_state_revisits`：一次实际写入后，文件内容回到本 run 已访问状态的次数；
- `dm_edit_cycle_blocks`：可在执行前准确预测的 canonical 内容锚定 `edit_file` 二周期被
  拦截的次数。

官方 harness 会忽略这些 `dm_*` 诊断列，但它们能把轨迹机制变化与 resolved rate 的高噪声
分开。正常完成一次 Agent run 时，字段存在且为 0 才表示“实测为零”；旧 predictions、
`agent_exception` 或 `harness_error` 缺少 `dm_diagnostics_version` 或某个诊断字段时表示
**未测量**，不能补 0 参与验收。

### 5. 进度环守卫只住在 SWE-bench 预测层

第一次真实复跑证明，两个原始机械根因修掉后，`astropy-14096` 会迁移到新的固定点。因此
新增 `swebench_verified/progress_guard.py`，只由 `predict.py` 装配，不影响主 CLI 或 30 题
benchmark：

- 精确重复 `search_in_file` 以完整参数和目标文件内容 SHA-256 为键；只缓存成功搜索，文件
  内容变化后缓存立即失效。拦截时完整回放已经过 `ObservationBounder` 限制的原观察，trace
  写入失败也不改变放行/拦截决定；
- 编辑状态按文件内容指纹记录，允许一次实际撤销；第二次试图通过内容锚定编辑进入已访问
  状态时，才在执行前拦截。

执行前预测只对 `old_string/new_string` 在当前内容中唯一命中的 canonical 内容锚定
`edit_file` 成立。行号 `edit_file` 和 `create_file` 只在写后记录状态回访，不承诺提前
拦截；`run_shell` / `run_python` 即使改了文件，也不计为本守卫的状态转移。

## 为什么不做的两件事

- **不关闭整个 edit guard。** 行号模式的旧坐标确实会漂移；本地 trace 中已有重读后把
  目标区间从旧行号改到新行号的实例。
- **不加“重复 N 次就熔断”的通用模块。** devlog 33 已删除无法证伪的工具熔断；本轮有
  可直接修复且已有真实轨迹证据的固定点。新增守卫限定在 SWE-bench 预测层，只识别可由
  参数和文件内容精确证明的重复状态，不复活跨工具、跨任务的内核行为算法。

## 三轮真实复跑

三轮均为 DeepSeek `deepseek-chat`、temperature 0、`--max-steps 60` 的定向复跑。它们用于
验证空 patch 机制，不是独立随机样本，也不能直接与首轮 10 题拼成一个新的总体 resolved
rate。

### 第一轮：机械修复有效，但 14096 迁移到重复搜索

预测：`swebench_work/preds-emptyfix-2-20260806.jsonl`；trace：
`swebench_work/traces-emptyfix-20260806/`。

- `astropy-13579` 的 edit guard block 从 **11 → 0**，实际执行 2 次内容锚定编辑，产出
  **1881 B** patch。说明 mode-aware freshness 与 no-op 契约消除了旧守卫损耗。
- `astropy-14096` 的解析失败从 **27 → 3**，且 3 次都对应上下文省略；原来的 malformed /
  `read_file` 二周期消失。但它仍然 0 次编辑、0 B patch：52 次 `search_in_file` 中，完全
  相同的 `def __getattr__` 搜索出现 **39 次**。机械修复没有解决探索固定点，只让下一层
  瓶颈显形。

### 第二轮：全局 progress prompt 是负面结果

预测：`swebench_work/preds-emptyfix-searchguard-14096-20260806.jsonl`；trace：
`swebench_work/traces-emptyfix-searchguard-20260806/`。

中间版本同时加入精确重复搜索守卫与一条全局 progress prompt。结果仍是 **0 B patch**；
模型不再反复搜索，却在 `raise AttributeError(...)` 的 `from None` 上来回切换：54 次
`edit_file` 中，27 次添加、27 次删除，最终精确回到原文件。这个 prompt 没有形成可证伪的
局部契约，只把搜索循环迁移成编辑二周期，因此已经从最终代码移除；负面结果保留在这里。

### 第三轮：纯事件守卫把空 patch 清零

预测：`swebench_work/preds-emptyfix-progressguard-14096-20260806.jsonl`；trace：
`swebench_work/traces-emptyfix-progressguard-20260806/`。

移除全局 prompt，只保留按事件和内容状态判定的 SWE-bench 专用守卫。`astropy-14096`
记录 `dm_repeat_search_blocks=1`，执行 2 次编辑，最终产出 **913 B** patch；本次轨迹没有
进入编辑撤销二周期，所以 `dm_edit_state_revisits=0`、`dm_edit_cycle_blocks=0`。至此预先
固定的主指标“空 patch 数”达到 **2 → 0**。

但这条轨迹仍跑满 60 步：44 次 `run_python` 中有 **35 次参数逐字相同**。这是一处明确的
残余固定点，也是 14096 没修好的直接线索；当前没有把搜索守卫未经设计地泛化成通用执行
熔断器。

## 官方 harness 结果

最终合并预测为 `swebench_work/preds-emptyfix-final-2-20260806.jsonl`，官方 swebench 4.1.0
汇总已归档为 `bench_reports/swebench-emptyfix-2-20260806.json`，逐题证据在
`logs/run_evaluation/emptyfix-2-20260806/dm-agent-deepseek/<instance>/report.json`：

| 实例 | patch | FAIL_TO_PASS | PASS_TO_PASS | 官方结论 |
| --- | ---: | ---: | ---: | --- |
| `astropy-13579` | 1881 B | **1/1** | **40/40** | **RESOLVED** |
| `astropy-14096` | 913 B | **0/1** | **426/426** | unresolved，零 P2P 回归 |

汇总是 submitted 2、empty patch **0**、resolved **1/2**、harness error 0。13579 的预测来自
第一轮，早于三个进度环诊断字段，因此这些字段缺失表示未测量，不应回填为 0。14096 则再次
证明：非空 patch 与 P2P 零回归都不等价于 F2P 已修好。

这份官方结果是两份**实际运行过的实验快照**合并判分，不是提交前工作树重新跑出的冒充
数字：13579 来自机械修复轮，14096 来自第三轮纯事件守卫。真实复跑后，契约审查又把编辑
二周期预判收紧为 canonical 内容锚定 `edit_file`，并补掉 `create_file`、冲突参数与行号模式
的误拦回归；14096 的实测轨迹中 `dm_edit_state_revisits=0`、`dm_edit_cycle_blocks=0`，没有
进入这些被收紧的分支。本轮没有额外消耗模型调用伪称重跑，收紧后的代码只声明确定性回归
与完整项目验证，不把 1/2 说成提交后源码树的新端到端分数。

## 验证口径

确定性回归覆盖：连续内容锚定编辑、内容编辑后切回行号模式、identity no-op 不落盘且不推进
台账、解析失败原文可审计、实时上下文与 `rebuild_context` 使用同一占位、旧 parse_error
日志保持原语义。

机械修复阶段曾完成 `python -m pytest` **492 passed**，加入初版 SWE-bench 进度环守卫后
相关定向回归为 **38 passed**。完成 canonical 内容编辑预测的契约收紧后，提交前重新跑完整
清单：compileall 通过；`python -m pytest` **503 passed**；eval 56/56、gate 1.000；ruff、
black、mypy、`uv lock --check` 全绿；coding / maintenance 两条 manifest guard 均
`compatible`；pre-commit 的 ruff / black / mypy / pytest 四个 hook 全部 Passed。

真实两题的主指标与结果：

| 指标 | 基线 | 结果 |
| --- | ---: | ---: |
| 空 patch | 2 | **0** |
| `astropy-13579` 的 guard block | 11 | **0** |
| `astropy-13579` patch | 0 B | **1881 B** |
| `astropy-14096` patch | 0 B | **913 B** |
| `astropy-14096` 解析失败上下文省略 | 0 | 最终轮 **5/5** 次对应 |
| `astropy-14096` 精确重复搜索拦截 | 未测量 | **1** |

这些直接计数不受官方 resolved 判分噪声影响，所以可以确认循环治理达到了目标；官方
F2P/P2P 则负责回答“题目是否真的修好”。两套口径必须同时保留。
