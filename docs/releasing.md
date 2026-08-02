# 发布到 PyPI

这份文档解释**为什么这么发**，以及每一步在做什么。第一次发布请整篇读完。

> PyPI 的网页界面偶尔会调整，以 <https://docs.pypi.org/trusted-publishers/> 为准。
> 本文描述的字段含义不会变，位置可能变。

## 为什么不用 API token

发布 PyPI 有两种认证方式：

| | API token | Trusted Publishing（本项目用的） |
| --- | --- | --- |
| 是什么 | 一串长期有效的密码，存在 GitHub Secrets 里 | GitHub 每次运行时向 PyPI 出示一张一次性身份证明 |
| 泄露风险 | token 泄露 = 别人能冒充你发包 | 没有长期凭证可泄露 |
| 维护 | 要记得轮换、离职要撤销 | 无 |
| 配置 | 生成 token → 存进 Secrets | 在 PyPI 上登记"我信任这个仓库的这个文件" |

Trusted Publishing 用的是 OIDC：GitHub Actions 运行时会生成一张短期令牌，里面写明
"我来自 `hwfengcs/DM-Code-Agent` 仓库的 `release.yml`"。PyPI 核对这条信息与你事先
登记的是否一致，一致才允许上传。**仓库里不需要存任何密码。**

这也是为什么 `.github/workflows/release.yml` 里有 `permissions: id-token: write`——
那是在向 GitHub 申请签发这张令牌的权限。

## 一次性设置

### 1. PyPI 账号

1. 注册 <https://pypi.org/account/register/>
2. **启用 2FA**（PyPI 强制要求）。用手机上的 authenticator app 扫码即可。
3. 把恢复码存好——2FA 设备丢了要靠它找回账号。

TestPyPI 是一个独立的演练环境，账号不通用，需要单独注册：<https://test.pypi.org/account/register/>

### 2. 登记 trusted publisher

因为 `dm-code-agent` 这个包**还不存在**，不能进项目设置页去加，要用 **pending publisher**
（"等这个包第一次被发布时，按这条规则放行"）：

前往 <https://pypi.org/manage/account/publishing/>，填：

| 字段 | 值 |
| --- | --- |
| PyPI Project Name | `dm-code-agent` |
| Owner | `hwfengcs` |
| Repository name | `DM-Code-Agent` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

TestPyPI 同样操作一遍（<https://test.pypi.org/manage/account/publishing/>），
唯一区别是 **Environment name 填 `testpypi`**。

> Environment 必须与 `release.yml` 里 `environment: name:` 的值**逐字一致**，
> 否则 PyPI 会拒绝上传。这是一层额外的保险：即使有人在仓库里加了别的 workflow，
> 只要 environment 对不上就发不出去。

### 3. GitHub Environments

仓库 → Settings → Environments，新建两个：`pypi` 和 `testpypi`。

给 `pypi` 加一条 **Required reviewers**（把你自己加上）。加了之后，正式发布会**停下来
等你在网页上点一次确认**才继续。tag 推错了还有机会拦住——这是不可逆操作前的最后一道闸。

## 每次发版

### 第一步：先发 TestPyPI

仓库 → Actions → Release → Run workflow，target 选 `testpypi`。

它会先跑完整验证（测试、eval gate、lint、类型、前端产物比对），构建 wheel 与 sdist，
然后在 Ubuntu 和 Windows 上**把 wheel 装进干净环境**验证七个命令可用、UI 在包里、
配置路径不落进 site-packages、Web 服务能起。全过了才上传。

装下来试一次：

```bash
pip install -i https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            "dm-code-agent[web]"
```

`--extra-index-url` 不能省：TestPyPI 上没有 fastapi、openai 这些依赖，得让 pip 回正式源找。

### 第二步：确认无误后发正式版

```bash
git tag v2.0.0
git push origin v2.0.0
```

tag 一推，`publish-pypi` 就会跑同一套验证，然后停在 `pypi` environment 等你点确认。

### 版本号规则

- tag 必须是 `v` + `pyproject.toml` 里的 `version`，workflow 会核对，对不上直接失败。
- **PyPI 的版本号是一次性的。** 发过的号删掉也不能重传——这是 PyPI 的硬规则，不是配置项。
  发错了只能发下一个号（`2.0.1`）。
- TestPyPI 同样一次性。演练时如果要试第二次，把 version 改成 `2.0.0.dev1`、`.dev2`……

## 出问题了怎么办

| 症状 | 原因 |
| --- | --- |
| `invalid-publisher` | PyPI 上登记的 owner/repo/workflow/environment 有一项对不上 |
| 卡在 waiting | `pypi` environment 的 required reviewer 在等你点确认 |
| `File already exists` | 这个版本号已经用过，改版本号 |
| 装下来没有 Web 界面 | 前端产物没重建就提交了；CI 的 `web` job 会拦，别绕过它 |

## 发布之后

- **改不了**。能做的只有 "yank"（标记为不推荐，已装的人不受影响，新用户不会装到）。
- 包名 `dm-code-agent` 从此归你，别人不能再用。
- 第一次发布成功后，pending publisher 会自动转成项目的正式 publisher，后续发版不用再配。
