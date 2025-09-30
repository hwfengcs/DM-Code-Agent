# DeepSeek ReAct 智能体

本项目提供了一个基于 Python 的 ReAct（推理 + 行动）智能体，使用 DeepSeek 模型进行推理，
同时调用本地工具来检查文件系统、创建 Python 文件并运行命令。

## 前置要求

- Python 3.9 或更高版本
- DeepSeek API 密钥（在 `DEEPSEEK_API_KEY` 环境变量中设置值或通过 `--api-key` 参数传递）

安装依赖：

```bash
pip install -r requirements.txt
```

## 运行智能体

在命令行直接传递自然语言任务：

```bash
python main.py "创建一个打印 hello world 的 hello.py 文件，运行它并显示输出。"
```

或者不带位置参数以交互方式启动，然后粘贴多行请求：

```bash
python main.py --show-steps
```

可选参数：

- `--model`: 选择 DeepSeek 模型（默认 `deepseek-chat`）
- `--max-steps`: 限制推理/工具迭代次数的上限（默认 `8`）
- `--temperature`: 调整采样温度（默认 `0.0`）
- `--show-steps`: 打印每个中间步骤的思考、行动和观察结果

内置工具支持列出目录、读写文件、执行 shell 命令以及运行 Python 代码或脚本——智能体构建和执行 Python 程序端到端所需的一切功能。
