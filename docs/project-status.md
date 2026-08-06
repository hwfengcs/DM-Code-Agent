# 项目现状与对标

这一页收的是「宣传性内容」：和同类项目的对比、算法模块的落地状态、评测口径的免责说明、
以及 roadmap。刻意从 README 里搬出来，因为它需要频繁更新，而 README 应该保持稳定。

## 一个必读的口径说明

**本项目不声明任何未实际运行过的评测分数提升。**

旧 SWE-bench Lite / Docker Tier-2 verifier / 跨模型跑分**冻结**，且 v2.1 已把
SWE-bench Lite 子系统整个移除：它跑不通（Tier-1 baseline 0.0% resolved，且受 host
verifier 环境噪声污染，按本项目自己的口径就不能与官方 leaderboard 比较），
Tier-2 verifier 从未实现，CI 也从不跑它。独立的 `swebench_verified/` 子系统随后使用
官方 SWE-bench 4.1.0 harness 完成了一轮真实跨仓库运行：20 题 11/20（55%），50 题
21/50（42%），最终报告 error=0；详见 [devlog 42](research-log/42-swebench-crossrepo-50.md)。

**本项目的记分牌是自带的 coding + maintenance benchmark**：**30 道题**（coding 15 + maintenance 15），本地建工作区 →
agent 改代码 → 加隐藏测试 → pytest 判定 pass/fail，产出 `overall_pass_rate`。
它不依赖 Docker、不依赖 HuggingFace，需要一个真实 API key。已实测：DeepSeek 在
**30 题**（coding 15 + maintenance 15）。13 题时代的存档 baseline 是
**pass_rate 0.385（5/13）**，95% CI [0.177, 0.645]（`bench_reports/baseline-20260803.json`）；
同一份报告里隐藏测试通过率是 **0.769**——落差来自「改了不该改的文件」（3 题）与
「步数耗尽」（4 题），不是写不出代码。该报告对应旧任务集，**不可与 30 题分数直接比较**。

读这个分数时请记住：30 题的规模下，**一题翻转就是 ±3.3 个百分点**（这是分辨率，不是实测噪声）；repeat-3 的经验噪声底约为 ±5 题。它适合用来对照
「改了策略之后有没有变好」，不适合当作与其他项目横向比较的绝对值。所有离线报告都附 raw JSON。

## v.s. 同类项目（当前公开口径）

> 这张表在 `README.md` / `README_EN.md` 首页也有一份，两处同源——改动请同步，
> 尤其是 SWE-bench Lite 那一行的 ⚠️ 与「非官方口径」说明，**不许在首页悄悄去掉**。

| 维度 | DM-Code-Agent | Aider | OpenHands | SWE-agent | smolagents |
| --- | --- | --- | --- | --- | --- |
| 本地优先（无沙箱依赖） | ✅ | ✅ | docker | docker | ✅ |
| 会话日志 + Replay | ✅ JSONL 条目树 + dry/tool replay + diff + fork | git diff | server log | trajectory | 弱 |
| 非破坏式上下文折叠 | ✅ 原文不删，可离线重算 | repo-map | partial | trajectory | weak |
| 扩展系统（不改内核加能力） | ✅ entry_points + 目录 + 显式文件 | ❌ | plugins | ❌ | ❌ |
| 可拦截生命周期钩子 | ✅ 6 个事件 | ❌ | partial | ❌ | ❌ |
| MCP 集成 | ✅ | ❌ | ✅ | ❌ | ❌ |
| 自带 hidden-test benchmark | ✅ 30 题，可出分 | ❌ | ❌ | SWE-bench | ❌ |
| 公开 SWE-bench Lite 分数 | ❌ 已移除（跑不通，见上） | ❌ | ✅ | ✅ | ❌ |
| SWE-bench Verified（本地跨仓库实测） | ✅ 50 题，官方 harness，21/50 | — | — | — | — |
| License | MIT | Apache-2.0 | MIT | MIT | Apache-2.0 |

## 算法模块状态

| 模块 | 状态 | 说明 | Devlog |
| --- | --- | --- | --- |
| ReAct + Planner + Replan | ✅ v1.5 | 基础 ReAct 循环 + 3–8 步全局计划 + 失败 replan | [00](research-log/00-kickoff.md) |
| 自带 hidden-test benchmark | ✅ 现役记分牌 | coding 15 题 + maintenance 15 题，出 `overall_pass_rate` | [09](research-log/09-maintenance-realism.md) |
| Mem0 风格上下文记忆 | ✅ 现役 | 原子记忆 + 按任务召回 + 保留最近轮次原文 | [24](research-log/24-memory-hygiene-and-recall.md) |
| Adaptive Replanning + token economics | ✅ 实现落地 | 错误信号映射到 replan 策略；离线统计 token / cost-per-success | [05](research-log/05-adaptive-and-economics.md) |
| 长上下文护栏 | ✅ 默认开 | 观察截断 + 分页提示、预算触发折叠、read-before-edit 拦截 | [23](research-log/23-observation-truncation-and-token-budget.md) |
| 状态容错 | ✅ 默认开 | 统一重试、原子写 + 备份、checkpoint/resume、进度保留 replan | [25](research-log/25-unified-llm-retry-and-atomic-io.md) [26](research-log/26-run-checkpoint-and-progress-carrying-replan.md) |
| Evals 闭环 | ✅ CI 门禁 | 恢复成功率、per-tag 能力画像、幻觉代理指标、repeat 方差、100% eval 门禁 + manifest 守卫 | [28](research-log/28-evals-recovery-capability-and-gates.md) |
| 扩展系统 + 生命周期钩子 | ✅ 架构升级 | 注册表 + 三来源发现 + 6 个可拦截事件；可选能力搬出内核 | — |
| 会话树 + 非破坏式折叠 + fork | ✅ 架构升级 | 条目带 id/parent_id，folding 只追加不删除，`dm-agent-trace fork` | [29](research-log/29-session-tree.md) |
| 减法重构 | ✅ v2.1 | 移除跑不通的 SWE-bench 与 6 个无法毕业的默认关模块，CLI 开关 35 → 23 | [33](research-log/33-scope-reduction.md) |

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

**已移除**（不是冻结，是删掉了）：SWE-bench Lite 子系统、Reflexion / Critic /
Self-Consistency / 工具熔断 / 记忆卫生 / LLM 摘要压缩。理由见
[devlog 33](research-log/33-scope-reduction.md)。

**冻结项**：旧 Docker/Tier-2 verifier、真实 cross-model 跑分。SWE-bench Verified 的本轮
50 题结果已归档；后续只做固定 sentinel repeat 或离线失败分析，不把 20→50 当独立复验。

短期在做的非算法方向：

- **压缩粘性实验**：现在折叠不是粘性的（某步折叠后，下一步若不满足触发条件仍发全量历史）。
  有了 `compaction` 条目后，这件事可以离线评估收益再决定改不改。
- **会话写入多 sink**：`message` / `compaction` 条目目前只跟 `--trace` 走，
  单独用 `--checkpoint` 时会话日志只有 checkpoint 条目。
- **扩展分发**：`dm-agent install <git-url>` 或 pip 包形式安装第三方扩展。
- **Maintenance benchmark 扩展**：文档一致性、CI 配置修复、跨文件重构、多轮修复任务。

完整的历史条目见 [CHANGELOG.md](../CHANGELOG.md)，设计决策见
[`docs/research-log/`](research-log/)。
