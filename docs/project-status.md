# 项目现状与对标

这一页收的是「宣传性内容」：和同类项目的对比、算法模块的落地状态、评测口径的免责说明、
以及 roadmap。刻意从 README 里搬出来，因为它需要频繁更新，而 README 应该保持稳定。

## 一个必读的口径说明

**本项目不声明任何未实际运行过的评测分数提升。**

真实 SWE-bench / Docker Tier-2 verifier / 跨模型跑分目前**冻结**。已发布的
SWE-bench Lite Tier-1 baseline（DeepSeek，固定 50 题子集）是
**0.0% resolved / 72.0% patch-applied**，这个数字受 host verifier 环境噪声影响，
**不能和官方 leaderboard 直接比较**。

所以 v2 的算法模块（Reflexion / Critic / Self-Consistency / Adaptive Replanning）只声明
「代码、keyless 测试和离线报告能力已落地」，不声明真实分数提升。所有离线报告都附 raw JSON。

## v.s. 同类项目（当前公开口径）

| 维度 | DM-Code-Agent | Aider | OpenHands | SWE-agent | smolagents |
| --- | --- | --- | --- | --- | --- |
| 本地优先（无沙箱依赖） | ✅ | ✅ | docker | docker | ✅ |
| 会话日志 + Replay | ✅ JSONL 条目树 + dry/tool replay + diff + fork | git diff | server log | trajectory | 弱 |
| 非破坏式上下文折叠 | ✅ 原文不删，可离线重算 | repo-map | partial | trajectory | weak |
| Reflexion / Critic / Self-Consistency | ✅ v2（默认关） | ❌ | partial | ❌ | ❌ |
| 扩展系统（不改内核加能力） | ✅ entry_points + 目录 + 显式文件 | ❌ | plugins | ❌ | ❌ |
| 可拦截生命周期钩子 | ✅ 6 个事件 | ❌ | partial | ❌ | ❌ |
| MCP 集成 | ✅ | ❌ | ✅ | ❌ | ❌ |
| 自带 maintenance benchmark | ✅ 6+ tasks | ❌ | ❌ | SWE-bench | ❌ |
| 公开 SWE-bench Lite 分数 | ⚠️ Tier-1：0.0%（50/300 子集，非官方口径） | ❌ | ✅ | ✅ | ❌ |
| License | MIT | Apache-2.0 | MIT | MIT | Apache-2.0 |

## 算法模块状态

| 模块 | 状态 | 说明 | Devlog |
| --- | --- | --- | --- |
| ReAct + Planner + Replan | ✅ v1.5 | 基础 ReAct 循环 + 3–8 步全局计划 + 失败 replan | [00](research-log/00-kickoff.md) |
| SWE-bench Lite suite | ✅ P1 | 50 题子集，Tier-1 baseline 含失败模式分析与 host 噪声说明 | [01](research-log/01-swebench-baseline.md) |
| Reflexion（episodic memory） | ✅ 实现落地 | ablation 待真实评测解冻 | [02](research-log/02-reflexion.md) |
| Mem0 风格上下文记忆 | ✅ 现役 | 原子记忆 + 按任务召回 + 保留最近轮次原文 | [24](research-log/24-memory-hygiene-and-recall.md) |
| Critic + Self-Consistency | ✅ 实现落地 | 完成前 peer-review 门禁 + N 路选优（majority / critic score / test pass） | [04](research-log/04-critic-and-consistency.md) |
| Adaptive Replanning + token economics | ✅ 实现落地 | 错误信号映射到 replan 策略；离线统计 token / cost-per-success | [05](research-log/05-adaptive-and-economics.md) |
| 长上下文护栏 | ✅ 默认开 | 观察截断 + 分页提示、预算触发折叠、read-before-edit 拦截 | [23](research-log/23-observation-truncation-and-token-budget.md) |
| 状态容错 | ✅ 默认开 | 统一重试、原子写 + 备份、checkpoint/resume、进度保留 replan；熔断默认关 | [25](research-log/25-unified-llm-retry-and-atomic-io.md) [26](research-log/26-run-checkpoint-and-progress-carrying-replan.md) [27](research-log/27-tool-circuit-breaker-experiment.md) |
| Evals 闭环 | ✅ CI 门禁 | 恢复成功率、per-tag 能力画像、幻觉代理指标、repeat 方差、100% eval 门禁 + manifest 守卫 | [28](research-log/28-evals-recovery-capability-and-gates.md) |
| 扩展系统 + 生命周期钩子 | ✅ 架构升级 | 注册表 + 三来源发现 + 6 个可拦截事件；可选能力搬出内核 | — |
| 会话树 + 非破坏式折叠 + fork | ✅ 架构升级 | 条目带 id/parent_id，folding 只追加不删除，`dm-agent-trace fork` | [29](research-log/29-session-tree.md) |

## 架构升级批次（2026-07）

对标 [Pi Agent Harness](https://github.com/earendil-works/pi-mono) 做的八步重构，
每一步都要求 eval 结果与重构前逐字段一致：

| # | 内容 |
| --- | --- |
| 1 | 扩大 ruff 规则集（`E F I UP B SIM TID RUF`）、引入 mypy、引入 `uv.lock` |
| 2 | `main.py` 搬进 `dm_agent/cli/`，修掉顶级 `main` 模块的打包 bug |
| 3 | 生命周期事件总线 + 三个核心可拦截钩子 |
| 4 | 扩展注册表 + 三来源发现机制 + 项目本地扩展信任模型 |
| 5 | Reflexion / Critic / 熔断 / read-before-edit 守卫全部改造成事件处理器 |
| 6 | 拆 `agent.py`（1616 → 866 行），每步环节独立成同层模块 |
| 7 | 会话树、非破坏式折叠、`fork` 子命令 |
| 8 | 文档重构（本批文档） |

## Roadmap

**冻结项**：Docker/Tier-2 SWE-bench、真实 cross-model 跑分，以及任何 v2 机制的
真实分数提升声明。

短期在做的非算法方向：

- **压缩粘性实验**：现在折叠不是粘性的（某步折叠后，下一步若不满足触发条件仍发全量历史）。
  有了 `compaction` 条目后，这件事可以离线评估收益再决定改不改。
- **会话写入多 sink**：`message` / `compaction` 条目目前只跟 `--trace` 走，
  单独用 `--checkpoint` 时会话日志只有 checkpoint 条目。
- **扩展分发**：`dm-agent install <git-url>` 或 pip 包形式安装第三方扩展。
- **Maintenance benchmark 扩展**：文档一致性、CI 配置修复、跨文件重构、多轮修复任务。

完整的历史条目见 [CHANGELOG.md](../CHANGELOG.md)，设计决策见
[`docs/research-log/`](research-log/)。
