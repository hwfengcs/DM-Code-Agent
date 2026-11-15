# 三份审计报告的落实记录（2026-11-15）

基于 `67fd4ea` 及中断后保留的 3 处配置改动、2 个辅助模块继续。
复核 [13 日](audit-2026-11-13.md)、[14 日](audit-2026-11-14.md)、[15 日](audit-2026-11-15.md)
报告，已在后续提交解决的条目不重复修改；本文件追加结果，不改写原报告。

## 已落实的决定

| 问题组 | 修复与契约 |
| --- | --- |
| 无限执行/输出增长 | Python、Shell、测试、lint 共用有限执行器；默认 120 秒、每流 8 MiB，最多多保留一次 8192 字节读取。超限停止进程树并返回失败；完整已捕获字节保留在系统临时目录的唯一子目录。 |
| 进程回收 | Windows 子进程挂起后加入 kill-on-close Job Object 再恢复，父进程先退出也可关闭整个 Job；Web 刷新/关闭和 MCP 停止均释放树及管道。POSIX 保证专用进程组内后代，主动脱组不在保证内。 |
| Web/CLI 配置 | Web 显式 `--no-config`，界面默认值和请求值是参数真相源；CLI 双向布尔开关及字段类型校验。交互菜单与 stdin 对话未实现的保存组合明确拒绝。库 max_steps 必须为正整数。 |
| 执行状态 | 小观察上限保留退出状态尾部；unittest 单文件使用 discover，支持绝对路径，并向上查找包根以保留相对导入。 |
| MCP | 仅在调用发送前重连；响应丢失后不自动重放。Windows 不隐式启用 shell；标准 npm/npx 包装器解析为 Node CLI。分页发现、游标循环拒绝、100 条通知消费及有限响应队列。 |
| SDK | 原生角色消息；max_tokens 映射；GPT-5/o 系列保守省略 temperature/top_p；Claude 多 system 与版本头；DeepSeek 普通 400 不再默认重试，显式 retry_status_codes 仍可定制。 |
| 用户轮次 | conversation_start 声明新协议；每任务 turn_start/turn_end，异常也记录；内部 run_end 重试不影响 busy。旧日志保留 run_end 回退。 |
| 摘要/诊断 | 按 run_start 分段，默认最后一段；API/CLI 可选旧段，Web 切段同步摘要与诊断。完成否决新增结构化事件。 |
| 记忆/钩子 | 来源感知的共享失败分类；读取 Error 类不再变成失败记忆；按实际压缩窗口预算触发，已折叠消息不重复提取；失败钩子的 JSON 嵌套参数深复制回滚。 |
| 长日志 | 不变文件解析缓存最多 32 文件/16 MiB 原文件大小；卡片、结束运行和扫描缓存分别有数量上限。SSE 按 ID 查重并以 16ms 批量发布；中断历史不显示仍在运行；非法路由返回列表。 |
| 折叠统计 | sticky_reuse 不算新压缩；条目 ID 去重，显示最近窗口收益，避免把重叠压缩收益相加。 |
| 技能/索引 | 校验 JSON 技能字段，英文词边界与中文子串匹配；新增用户目录，项目自动执行仍走扩展信任机制。评测只加载内置技能。索引提前停止扫描，标明截断并逐文件报告解码/解析错误。 |
| 评测输入 | 未知、混合无效或空任务/变体拒绝；预算与价格校验；success 必须 bool，声明任务/变体/重复数必须与结果一致；gate 核对原始结果。 |
| 统计口径 | reported tokens 与无 usage 时的估算逐请求累计，额外公开 usage_requests/estimated_fallback_tokens；request_count 仍是逻辑请求，重试计数独立。不同重复次数拒绝 score-diff；经济性从原始结果统计。 |
| SWE/缓存 | 预测与选择清单明确拒绝 null/list；坏缓存重取前保留字节备份；准备容器唯一命名，只清理本次创建的容器；非 UTF-8 文本补丁明确失败，不有损替换。未运行 Docker。 |
| 开发链/发布 | Vitest 4.1.12 与锁文件同步；重建静态资源。新增 v2.1.1，保留 v2.1.0，走现有 CI、Pages 与 Release 工作流。 |

## 保持或暂不扩大的范围

- JSONL 离线读取选择严格拒绝，补校验 metadata/steps；未实现自动有效前缀恢复。
  SSE 对未完整行继续等待，对坏行给出诊断；原件从不删除或修补。
- 未增加列表虚拟化、磁盘字节索引或完整分层 lint；当前先修已确定的重复工作与无界缓存。
- 外部 MCP 服务的发布/认证兼容性仍依外部文档；未联网启动所有示例。
- 官方 SWE-bench、Docker 和跨模型评分继续冻结；没有将离线回归当作模型能力提升。
- 经验噪声区间不等于统一统计检验，保留已有启发式阈值；历史研究日志中的损坏字符保留原文。
- Web fork 继续是日志分支，不假称恢复并重跑；重放副作用仍需显式参数。

## 验证

本地 Windows / Python 3.13.9，使用 `uv.lock` 与项目开发环境；没有把本地类型分支检查当作 Linux 实际运行。

- 全量 Python：906 passed、8 skipped；跳过项依平台条件，第三方 Starlette/httpx 有一条弃用提示。
  最后补充 MCP 通知并发保护后，执行、MCP、CLI 对话及审计契约回归 67 项全部通过。
- compileall、Ruff、Black、mypy、`uv lock --check` 通过；mypy 的 Windows 与 Linux 分支均通过。
- direct_finish smoke 通过；完整确定性 eval 为 14 任务 × 4 变体，共 56 次，全部成功且 gate 通过。
  本地结果 `eval_reports/audit-release-2.1.1.json` 不纳入历史归档；这不是实际模型能力评测。
- maintenance --list 通过；两套 manifest 与基线一致：coding `c846387398b2ab63`，maintenance `1a633dda3e5bda09`。
- 前端 62 项测试、TypeScript 和构建通过；完整 `npm audit` 为 0 vulnerabilities。
  用户轮次回归覆盖内部重试、最终回答与没有 run_end 的异常结束；两次构建产物一致。
- 缓存 fixture：20,000 条、1,797,780 字节，连续读取 10 页只解析 1 次，耗时 0.044 秒。
  这是本机合成日志测量，不能推断全部大型日志或浏览器长列表性能。
- wheel/sdist 构建成功。仓库外独立虚拟环境安装 wheel 后，九个命令入口、离线 demo、
  两份 HTML 证据导出、配置目录、随包 UI、GET / 与鉴权 /api/meta 全部通过。
  原始演示测试实际经历退出码 1 → 0；没有验证的案例继续报告 verification gap。

发布沿用仓库工作流；main 部署演示站，v2.1.1 标签生成 GitHub Release。
`PYPI_PUBLISH_ENABLED=false`，本次不启用或声称发布 PyPI。远端工作流结果另行追加。

### 首次推送与安装链补验

`b26b8e6` 的 [演示站部署](https://github.com/hwfengcs/DM-Code-Agent/actions/runs/43677699701)
成功，公开站点 HTTP 200。首次 CI 的前端安装发现锁文件遗漏 Tailwind WASI 的 bundled
依赖；此前已有 node_modules 的测试/构建不足以证明干净安装可复现。
在不含 node_modules 的临时目录中使用 CI 同系列 npm 10.9.9 重新解析原锁文件，保留顶层
依赖版本并补齐 bundled 条目。临时目录 npm ci、本仓库 npm ci、62 项前端测试、类型、构建
及完整 audit 通过；产物没有变化。另做 Linux 目标的 npm ci dry-run，实际 Linux 安装由 CI 验证。
