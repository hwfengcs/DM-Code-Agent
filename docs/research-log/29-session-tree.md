# 29 — 会话树、非破坏式压缩与 fork

## TL;DR

把 trace / checkpoint / 对话历史统一到**一种 append-only 会话条目格式**：每条带
`id` 与 `parent_id`，于是运行历史从「线性日志」变成「可导航的树」。在此之上：

1. **上下文压缩改为非破坏式**——压缩不再是「现算一份短消息、算完就丢」，而是往会话日志
   追加一条 `compaction` 条目（记下折叠了哪些条目、从哪条开始保留、摘要是什么），
   构造消息时按这条条目跳过折叠区间。**原始条目一条不删**，发给 LLM 的消息与改造前**逐字节一致**。
2. **checkpoint 退化成「记住某个 entry id」**——`--checkpoint x.jsonl` 写会话格式的
   append-only 日志，`--resume` 定位到其中一条 `checkpoint` 条目继续跑，
   `--resume-at <entry-id>` 可以挑更早的条目。
3. **新增 `dm-agent-trace fork <session.jsonl> --at <entry-id>`**——从任意条目分叉出新会话。

直接收益：`no_compression` ablation 从「只能比最终指标」升级成「能在同一份会话日志上
反复开关压缩重算上下文」，可以精确量化压缩折叠掉了什么。

## Context

`经验.md` 第三章指出，项目里「运行历史」是三套互不相通的东西：

- `dm_agent/tracing/` 写 JSONL，只读，只用于审计和回放；
- `dm_agent/core/checkpoint.py` + `core/persistence.py` 存独立快照，只用于 `--resume`；
- 对话历史活在 `ReactAgent.conversation_history` 内存里，`reset_conversation()` 直接清空。

结果是**能回放，但不能从历史某一步分叉重跑**，而「换个思路从第 5 步重来」恰恰是调试 agent
最有用的操作。

更关键的是压缩的可信度。改造前 `ContextWindow.build_messages()` 每一步都用
`compressor.compress(history)` 现算一份短消息发给 LLM——注意 `conversation_history`
**本来就没有被改写**，所以「原文被删掉了」这个描述并不准确；真正的问题是
**折叠事实没有落盘**：折叠了哪几条、摘要长什么样、`<agent_memory>` 注没注入，
trace 里一个字都没有。所以事后无法回答「压缩到底丢了什么」，`no_compression` ablation
也就只能比较最终成功率，无法归因。

## 最终的会话条目结构

```json
{
  "id": "a1b2c3d4-0007",
  "parent_id": "a1b2c3d4-0006",
  "timestamp": "2026-07-28T09:15:22.481923+00:00",
  "run_id": "a1b2c3d4e5f6...",
  "event": "tool_call",
  "payload": {"step_number": 3, "action": "read_file", "...": "..."}
}
```

- `id` = `f"{run_id[:8]}-{seq:04d}"`。可读、可手敲、可当 `--at` 的唯一前缀用；
  同一个 writer 内 `seq` 单调递增，因此一个文件里承载多次 run 也不会撞号。
- `parent_id` = 同一 writer 写出的上一条 entry 的 id；文件第一条为 `""`，
  fork 出来的会话第一条指回源会话的分叉点。
- `event` / `payload` **沿用现有拼写**，没有改名成 `type` / `data`。

### 为什么不改名成 `type` / `data`

`经验.md` 里写的目标结构是 `{id, parent_id, type, timestamp, data}`。落地时选择保留
`event` / `payload`，理由是成本收益完全不成比例：

- 改名要动 `tests/test_tracing.py`、`test_agent_events.py`、`test_agent_guards.py`、
  `test_agent_internals.py`、`test_checkpoint.py` 共约 20 处断言；
- 还要改 `dm_agent/benchmarks/runner.py` 与 `dm_agent/tracing/cli.py` 的全部读取路径，
  而「不许改 benchmarks 行为」是本次的硬约束；
- 换来的是零功能收益——`id` + `parent_id` 才是「树」的本质，键名不是。

所以本次是**纯增量的 envelope 升级**：老字段一个不动，新字段一律追加。
`TRACE_SCHEMA_VERSION` 从 `1.2` 升到 `2.0`，标记「条目开始带身份和父指针」。

### 新增的条目类型

| event | 何时写 | 关键 payload |
| --- | --- | --- |
| `message` | 每次往 `conversation_history` 追加消息 | `role` / `kind` / `content` 或 `content_chars`+`content_sha256` |
| `compaction` | 每次触发上下文折叠 | `first_kept_entry_id` / `folded_entry_ids` / `summary` / `trigger` |
| `checkpoint` | `--checkpoint *.jsonl` 每步落盘 | `step_number` / `state`（完整 `RunCheckpoint` 字典） |
| `fork` | `dm-agent-trace fork` 写新文件时 | `source` / `forked_from_entry_id` |

## 隐私：一种格式，两个保真档

「可恢复状态」天然含完整 `conversation_history`，里面有模型原始输出；而 trace 的隐私约定是
**默认只记摘要、自动脱敏、完整 LLM I/O 必须 `--trace-llm-io` opt-in**，这条不许放松。
两者直接冲突，所以本次的解法是**同一种格式、两个保真档、一套工具链**：

| | `--trace x.jsonl` | `--checkpoint x.jsonl` |
| --- | --- | --- |
| 定位 | 可分享的审计视图 | 本地的可恢复会话 |
| assistant 消息 | 只记 `content_chars` + `content_sha256`（`--trace-llm-io` 时才有全文） | 全文（与旧 `cp.json` 一致） |
| 脱敏 | 是 | `checkpoint` 条目不脱敏（脱敏会把 `$HOME` 改写成 `~`，污染续跑的上下文） |
| 工具 | `view` / `analyze` / `replay` / `diff` / `fork` | 同上，外加 `--resume` |

`message` 条目里 user 消息记全文——这不是放松，因为 `tool_call.observation` 与
`step.observation` 今天默认就是全文记录的，user 消息的内容正是它们的包装；
真正受管控的一直是模型原始输出，这条口径没有变。

两个参数指向**同一个文件时直接报错退出**：否则默认脱敏的分享档会被完整历史悄悄污染。

## 压缩非破坏化怎么做到「行为零变化」

改造前 `ContextCompressor.compress(history)` 返回
`system_messages + memory_messages + recent_messages`。核对后确认：
`conversation_history` 的 6 个写入点全是 `user` / `assistant`，**永远没有 `system` 消息**，
所以返回值恒等于「`<agent_memory>` 块 + 最近 `keep_recent*2` 条」。

于是把折叠决策与折叠动作拆开：

```python
compaction = compressor.plan_compaction(history)     # 折叠哪些、从哪条起保留、摘要是什么
messages   = apply_compaction(history, compaction)   # 按 compaction 重建消息
compress   = apply_compaction ∘ plan_compaction      # 旧 API 原样保留
```

`ContextWindow.build_messages()` 改成「先 `plan_compaction` → 写 `compaction` 条目 →
再 `apply_compaction`」。因为重建规则与原实现同构，**发出的消息逐字节一致**，
触发条件（`should_compress` 的 cadence / token budget）一个字没动。

有意**没有**顺手修的一件事：改造前后压缩都**不是粘性的**——某一步折叠了，
下一步若 `should_compress` 为假，仍然发全量历史。这看着像缺陷，但改它会改变真实
run 的行为，不该夹在一次「非破坏化」的重构里。留给后续单独实验。

### 这带来的 ablation 能力

`dm_agent/tracing/session.py` 提供：

```python
rebuild_context(entries, apply_compaction=True)    # 复现当时真正发给 LLM 的窗口
rebuild_context(entries, apply_compaction=False)   # 同一份日志，假装从没压缩过
```

两者相减就是「这次压缩折叠掉的原文」。这是 `no_compression` 变体从
「跑两遍比指标」升级到「同一次 run 内精确归因」的关键。

## 老 trace 文件的兼容

`load_trace_events()` 现在经 `session.py` 归一化后返回：缺 `id` 的条目按序补
`legacy-0000`、`legacy-0001`…，`parent_id` 补成前一条。因此：

- `dm-agent-trace view / analyze / analyze-dir / replay / diff` 对旧文件**行为不变**；
- `fork` 对旧文件同样可用（分叉点用合成 id），只是旧文件里没有 `checkpoint` 条目，
  分叉产物只能审计、不能 `--resume` 续跑——这种情况下 CLI 会明确提示，而不是默默失败。

`--resume` 对老 `*.json` 快照的处理完全不变：整文件能解析成一个 JSON 对象就走旧路径。

## `--resume` 的用户可见语义

| 写法 | 改造前 | 改造后 |
| --- | --- | --- |
| `--checkpoint cp.json` + `--resume cp.json` | 可用 | **完全不变** |
| `--checkpoint run.jsonl` + `--resume run.jsonl` | 不支持 | 新增：从最后一条 `checkpoint` 条目续跑 |
| `--resume run.jsonl --resume-at <entry-id>` | 不支持 | 新增：从指定条目**或之前**最近一条 checkpoint 续跑 |

即：**没有破坏性变更，只有增量**。`--resume` 与 `--enable-reflexion` 互斥的既有约束不变。

## 验收口径

1. **压缩非破坏性**：同一脚本任务开/关压缩各跑一遍，两份会话日志的 `message` 条目序列
   逐位一致，差异只出现在 `compaction` 条目上。
2. **resume 有效**：`--checkpoint run.jsonl` 跑到步数上限中断，`--resume run.jsonl` 续跑并成功。
3. **fork 有效**：从某条目分叉，新会话能 `--resume` 继续跑。
4. `python -m dm_agent.evals.cli` 与改造前逐字段一致；`optional_paths_probe` 的四条
   默认关闭路径除新增的 `message` / `compaction` 条目外逐字段一致。

## 落地后观察到的两件事

**1. 「压缩」有时会让上下文变大，现在这件事看得见了。**
第一次折叠的 compaction 条目实测：

```
trigger = 'token_budget'   folded_message_count = 1   kept_message_count = 17
estimated_tokens_before = 309   estimated_tokens_after = 329
```

只折叠了 1 条消息，却注入了一整块 `<agent_memory>`，净效果是上下文**增大** 20 token。
这不是本次改出来的 bug——改造前就是这个行为，只是当时没有任何记录，所以没人知道。
非破坏化的第一个实际收益就是把它暴露出来。后续可以在 `plan_compaction` 里加一条
「折叠收益为负就不折叠」的判据，但那是行为变更，不该夹在本次重构里。

**2.（已在第 9 步解决）`message` / `compaction` 条目跟着 `--trace` 走，不跟
`--checkpoint` 走。**
第 7 步只传 `--checkpoint x.jsonl` 时，会话日志里只有 `checkpoint` 条目。这不影响续跑与
fork（checkpoint 条目自带完整 `conversation_history`），但 `dm-agent-trace view`
会显示 0 步。第 9 步引入 `SessionWriter` 扇出后，checkpoint-only 文件也收到完整的
普通会话条目；trace 与 checkpoint 各自保留自己的隐私档和 entry id 映射：

```bash
dm-agent "task" --checkpoint sessions/run.jsonl
```

根因是 `ReactAgent` 只有一个 trace 汇。第 9 步把「会话写入」抽象成可扇出的多 sink；
checkpoint 状态条目只写本地完整档，完整 LLM I/O 仍需显式 `--trace-llm-io`。

## Open questions / next bets

- **压缩粘性**：见上文，改造后有了 `compaction` 条目，粘性压缩可以做成
  「沿用最后一条 compaction 的 `first_kept_entry_id`」，且能用同一份日志离线评估收益。
- **fork 后的分支管理**：目前 fork 只产出新文件，没有 `/tree` 式的分支导航与
  「切走的分支自动生成摘要」。等 fork 的实际用法沉淀后再定。
- **会话日志体积**：`message` 条目与 `tool_call` 条目内容有重叠（user 消息是 observation
  的包装），trace 体积约增加 30–50%。等真实使用后再决定是否给 `message` 做去重引用。
- **`--checkpoint` 单独使用时缺 message/compaction 条目**：第 9 步已用多 sink 扇出解决。
- **A-3（`build_user_prompt` 的死代码）**：resume 之后模型看不到「之前的步骤」摘要。
  有了 `message` 条目后，这个问题可以改成「从会话日志重建提示词」，但属于行为变更，
  仍按缺陷清单单独处理。
