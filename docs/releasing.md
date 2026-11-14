# 发布与安装

v2.1.0 的正式安装入口是 [GitHub Release](https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v2.1.0)
中的 wheel。PyPI 发布需要维护者先完成账号与 Trusted Publisher 绑定；在实际发布成功前，
不要把 `pip install dm-code-agent` 当作可用的安装入口，也不要把 CI 或 GitHub Release 成功视为 PyPI 发布成功。

## 从 GitHub Release 安装

建议在 Python 3.10+ 的虚拟环境中执行：

```bash
python -m pip install "dm-code-agent[web] @ https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl"
dm-agent-demo --output demo-run
dm-agent-trace export demo-run/sessions/verified.jsonl --output verified.html --include-content
dm-agent-web --read-only --sessions-dir demo-run/sessions
```

`demo-run` 必须是新目录或空目录。演示不需要 API key：决策由脚本提供，文件修改与 unittest
实际运行，不能当作模型能力或 benchmark 成绩。`verified.html` 是可离线打开的独立报告；
这里的 `--include-content` 用于公开演示 fixture。导出自己的会话时，默认省略正文，
显式包含正文的报告应先在本地检查再分享。

Release 同时提供源码包（`.tar.gz`）与 `SHA256SUMS`。下载两个包及校验文件后，
Linux 可用 `sha256sum --check SHA256SUMS`；PowerShell 可用 `Get-FileHash -Algorithm SHA256 <文件名>`
与 `SHA256SUMS` 对照。依赖仍由 pip 从包索引安装；离线 demo 指运行演示时不调用模型或网络，
不表示首次安装无需网络。

## 发布流程

[release.yml](../.github/workflows/release.yml) 的三个出口使用同一份已验证的 wheel 与 sdist：

| 触发方式 | 发布结果 |
| --- | --- |
| 推送 `v*` tag | 自动创建 GitHub Release，上传 wheel、sdist、`SHA256SUMS`，使用对应版本的发布说明 |
| 推送 `v*` tag，且 repository variable `PYPI_PUBLISH_ENABLED` 等于 `true` | 额外发布正式 PyPI；仍须满足 PyPI 账号绑定与 environment 规则 |
| 手动运行，target 选择 `testpypi` | 发布 TestPyPI；不会创建 GitHub Release 或发布正式 PyPI |
| 手动运行，target 选择 `none`（默认） | 只验证并保留构建产物，不发布 |

构建先检查 lockfile、测试、确定性 eval gate、lint、格式、类型与前端产物一致性。
随后 Ubuntu 和 Windows smoke job **不 checkout 仓库**，从构建的 wheel 安装，验证九个命令入口、
前端静态资源、包外配置路径与 Web 服务，并实际运行离线 demo 和两份 HTML 导出：

- 验证案例的 unittest 先失败，修复后四项通过，报告显示退出码与修改片段。
- 遗漏验证案例的报告指出 verification gap。

GitHub Release 和两个包索引发布 job 都等待 build 与全部 smoke job 成功。
`SHA256SUMS` 在 GitHub Release job 中生成，不进入 PyPI 上传目录。

### 每次发版

1. 更新包版本与 `uv.lock`，完成项目要求的本地验证。前端有变化时重建并提交静态资源。
2. 写好 `docs/release-v<版本>.md`。v2.1.0 对应 [`docs/release-v2.1.0.md`](release-v2.1.0.md)。
3. 提交、推送后，可先手动运行 Release workflow，target 选 `none` 检查构建与包外安装。
4. 推送与 `pyproject.toml` 版本完全一致的 tag：

```bash
git tag v2.1.0
git push origin v2.1.0
```

workflow 会校验 tag 版本与发布说明文件。全部检查通过后，`publish-github` 创建 Release，
正文取自 `docs/release-v2.1.0.md`。从 Release 下载 wheel 再检查一次安装和演示即可确认用户入口可用。
复跑一个已经创建过 Release 的 tag 不会覆盖原有资产；需要修复已发布包时应递增版本重新发布。

## 启用 PyPI 与 TestPyPI

GitHub Release 不依赖 PyPI 配置。包索引使用 **Trusted Publishing（OIDC）**，
workflow 不存储长期上传 token。`id-token: write` 只赋予两个包索引发布 job。

### 账号与 publisher 绑定

1. 注册 [PyPI](https://pypi.org/account/register/) 账号、启用 2FA 并保管恢复码。
   [TestPyPI](https://test.pypi.org/account/register/) 是独立环境，需要单独账号和绑定。
2. 如果项目尚不存在，在 [PyPI publishing 设置](https://pypi.org/manage/account/publishing/)
   创建 pending publisher；已存在且你有管理权限时，在项目设置中添加 publisher。
3. 填写下面的绑定字段；TestPyPI 在其 [publishing 设置](https://test.pypi.org/manage/account/publishing/)
   使用同样字段，仅 environment 改为 `testpypi`。

| 字段 | 正式 PyPI 的值 |
| --- | --- |
| PyPI Project Name | `dm-code-agent` |
| Owner | `hwfengcs` |
| Repository name | `DM-Code-Agent` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

4. 在 GitHub 仓库 Settings → Environments 建立 `pypi` 和 `testpypi`。
   environment 名称必须与 publisher 和 workflow 逐字一致。可以按维护需求配置 required reviewers；
   配置后对应 job 会等待人工审核。

字段与网页位置以 [PyPI 官方文档](https://docs.pypi.org/trusted-publishers/) 为准。

### 先验证 TestPyPI

仓库 Actions → Release → Run workflow，明确选择 `target=testpypi`。它会构建、跑完跨平台 smoke，
再上传 TestPyPI。版本不能重复上传；多次演练应使用新的开发版本，如 `2.1.1.dev1`、`2.1.1.dev2`。

确认 TestPyPI 发布成功后，将下面的版本替换为实际上传版本，在新的虚拟环境试装：

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "dm-code-agent[web]==2.1.1.dev1"
dm-agent-demo --output demo-run
```

额外索引用来获取 TestPyPI 未提供的依赖；固定版本可以确认测试的是刚上传的版本。

### 打开正式 PyPI 开关

只有在正式 PyPI publisher 绑定完成后，才在仓库 Settings → Secrets and variables → Actions → Variables
中设置 repository variable `PYPI_PUBLISH_ENABLED` 为字符串 `true`。也可使用：

```bash
gh variable set PYPI_PUBLISH_ENABLED --body true --repo hwfengcs/DM-Code-Agent
```

此后推送新版本 tag 才会运行 `publish-pypi`。未设置或值不为 `true` 时，该 job 会跳过，
GitHub Release 照常发布。正式 PyPI 与 GitHub Release 是独立出口；一个成功不代表另一个成功。
确认 PyPI 页面存在目标版本并成功试装后，才更新首页为包名安装命令。

## 常见失败

| 症状 | 排查方向 |
| --- | --- |
| `publish-pypi` 显示 skipped | repository variable 未设为 `true`，或本次不是 tag push；在账号绑定前这是预期行为 |
| `invalid-publisher` | 核对包索引中登记的 owner、repo、workflow、environment，并确认操作的是 PyPI 还是 TestPyPI |
| 卡在 waiting | 查看对应 environment 的 reviewer 或其他保护规则 |
| `File already exists` | 包索引版本已使用，递增版本；PyPI 与 TestPyPI 都不能重复上传同一文件名 |
| 缺少 release notes | 在 tag 指向的提交中添加对应 `docs/release-v<版本>.md`，再使用新的正确版本发布 |
| GitHub Release 已存在 | 不覆盖发布资产；确认既有发布状态，修复内容使用新版本 |
| 前端产物不一致 | 本地重新构建 `web/` 并提交 `dm_agent/server/static`，不要绕过构建检查 |

PyPI 发布后的文件不能原地修订；可 yank 有问题的版本，再发布新版本。
首次 pending publisher 成功后会转换为项目 publisher，后续沿用同一绑定。
