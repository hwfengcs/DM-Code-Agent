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

**第一步：预测**（在主 venv 里，需要 `.env` 的 API key）

```bash
python -m swebench_verified.run --limit 10 --max-steps 60 \
  --output swebench_work/preds.jsonl --trace-dir swebench_work/traces
```

每题会：拉官方评测镜像 → `docker cp` 出 `/testbed` 当工作区 → 跑 ReactAgent →
`git diff` 出 patch。断了用 `--resume` 接着跑。

**第二步：判分**（在 swebench venv 里）

```bash
PYTHONPATH=swebench_verified/_winshim \
  .swebench-venv/Scripts/python.exe -m swebench_verified.evaluate \
  --predictions swebench_work/preds.jsonl --run-id myrun --max-workers 4
```

产出 `dm-agent-<provider>.<run_id>.json`，逐题结果在 `logs/run_evaluation/<run_id>/`。
只想重看结论：`--summarize-only <report.json>`。

## 成本

| 项 | 量级 |
| --- | --- |
| 镜像 | **约 3.9 GB / 题**，下载是主要瓶颈（50 题 ≈ 196 GB） |
| 预测 | 约 40 秒 / 题（DeepSeek，简单题 8 步左右） |
| 判分 | 约 20 秒 / 题（复用已有镜像） |

工作区默认建在系统临时目录，跑完即删（`--keep-workspace` 可保留，几百 MB / 题）。

## 三个踩过的坑

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

另有一道安全闸 `_assert_git_root`：工作区必须自己就是 git 仓库根，否则拒绝执行
`git add -A`——否则 git 会向上查找，作用到本项目的仓库上（实测差点中招）。
