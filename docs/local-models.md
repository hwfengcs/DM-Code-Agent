# 连接 Chat Completions 服务：Xinference 与 Qwen

[English](local-models.en.md) · [快速开始](getting-started.md) · [扩展源码](../examples/openai_compatible.py)

这份配方连接一个已经启动、提供 OpenAI 兼容 **Chat Completions** 接口的模型服务。
模型下载、加载与推理由服务端负责。客户端以显式供应商扩展接入，不改变 Agent 主循环或四家内置供应商。

**验证范围：**真实 OpenAI SDK 配合内存 HTTP transport，覆盖请求路径、消息角色、鉴权隔离、
重试和空响应处理。这些是协议测试；目前没有归档真实 Xinference/Qwen 运行，不能据此承诺模型修复能力。

## 1. 确认服务与模型 ID

通过 Xinference 自己的界面启动 chat/instruct 模型。服务应在
`choices[0].message.content` 返回助手最终文本。使用常见默认端口时，模型列表地址为：

```text
http://127.0.0.1:9997/v1/models
```

记录响应里的模型 **ID/UID**，它不一定等于界面的展示名称。
给 DM 的 `base_url` 以 `/v1` 结尾，不要包含 `/chat/completions`。

服务启用了鉴权时，在目标工作区的 `.env` 中写入服务端密钥：

```dotenv
DM_COMPATIBLE_API_KEY=your-local-server-key
```

没有该变量且未传 `--api-key` 时，扩展使用 `local-no-key` 作为无鉴权服务的 SDK 占位值。
它不读取 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`，也不会在缺少 endpoint 时回退到云服务。

## 2. 加载扩展

按照[快速开始](getting-started.md)安装 release wheel。将
[`examples/openai_compatible.py`](../examples/openai_compatible.py) 保存到本地并审阅。
克隆仓库后可以直接使用该文件；这个新示例不在已发布的 v2.1.0 wheel 中。

在目标 Git 工作区执行，替换扩展的绝对路径和 `YOUR_MODEL_UID`：

```bash
dm-agent "读取 README，说明测试命令，不要修改文件。" --extension "/absolute/path/to/openai_compatible.py" --provider openai-compatible --base-url http://127.0.0.1:9997/v1 --model "YOUR_MODEL_UID" --max-steps 8 --trace sessions/local-review.jsonl --show-steps
```

Windows 路径可以写成 `"C:/projects/DM-Code-Agent/examples/openai_compatible.py"`。
`--extension` 会执行 Python 文件，只加载自己信任的源码。不要同时传 `--no-extensions`，
它会禁用这个供应商。每次显式传入服务提供的模型 UID。

内置 `--provider openai` 调用 `/responses`，只换 `--base-url` 不能解决协议不兼容。
这里的扩展调用 `/chat/completions`，保留消息角色，使用既有有界重试层，关闭 SDK 内层重试。

## 3. 做一次小修改，检查证据

只读请求成功后，在可审查的 Git 工作区选择一个已知缺陷：

```bash
dm-agent "为已知的重试次数边界缺陷补回归测试，修复条件，并运行相关测试。" --extension "/absolute/path/to/openai_compatible.py" --provider openai-compatible --base-url http://127.0.0.1:9997/v1 --model "YOUR_MODEL_UID" --max-steps 12 --trace sessions/local-repair.jsonl --show-steps
dm-agent-trace analyze sessions/local-repair.jsonl
dm-agent-trace export sessions/local-repair.jsonl --output local-repair.html
git diff
```

将示例任务替换为仓库中的实际问题。请求会消耗本地算力或服务端费用；步数限制约束 Agent 动作，
不是 token 费用或全部模型请求数的硬上限。检查改动并独立运行测试。
报告默认只有结构摘要；需要检查和分享脱敏片段时才加 `--include-content`。

DM 要求模型在普通助手文本里输出 JSON 动作，不使用服务原生的 function calling。
接口兼容不代表每个模型都能稳定遵循动作协议。

## 常见问题

| 现象 | 检查方向 |
| --- | --- |
| Connection refused | 模型服务是否启动，端口是否正确 |
| `/v1/v1/chat/completions` 返回 404 | 使用这份 SDK 扩展，base URL 只保留一个 `/v1` |
| `/responses` 返回 404 | 是否加载扩展并选择 `--provider openai-compatible` |
| Model not found | 使用 `/v1/models` 返回的真实 ID |
| 401 / 403 | 配置 `DM_COMPATIBLE_API_KEY`；鉴权错误不会自动重试 |
| 助手正文为空 | 模型应返回最终文本；只有 `reasoning_content` 不足以继续执行 |
| JSON 解析失败 | 检查模型指令遵循能力和上下文设置，先用小任务验证 |

不启动任何服务也能验证适配器：

```bash
uv run --frozen python -m pytest tests/test_openai_compatible_example.py
```

报告问题时附 DM 版本/提交、服务版本、模型 UID、接口路径（不含凭据）与错误信息即可，
不要粘贴密钥或未审阅的完整会话。
