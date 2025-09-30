# Your First AI Agent Project

<div align="center">

**Intelligent ReAct (Reasoning + Acting) Agent Based on Multiple LLM APIs**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) | **English**

</div>

## 📖 Project Overview

If you're just starting to learn about AI Agents and don't know where to begin, start with this project to learn or develop your own Agent applications.

This project provides all new AI Agent developers with an extremely low learning curve yet fully functional **ReAct (Reasoning + Acting) Agent**, supporting multiple large language models (DeepSeek, OpenAI, Claude, Gemini) for reasoning and local tool execution to complete various tasks. The agent can:

- 📁 **File Operations** - Create, read, and list files and directories
- 🐍 **Python Execution** - Run Python code and scripts
- 💻 **Shell Commands** - Execute system commands
- 🎯 **Task Completion** - Intelligently mark task completion status
- 🎨 **Interactive Interface** - User-friendly menu-based operation experience

## ✨ Key Features

### 🤖 Multi-Model Support ⭐ New
- **DeepSeek** - Default model, cost-effective
- **OpenAI** - GPT-3.5/GPT-4 series models
- **Claude** - Anthropic Claude 3.5 series
- **Gemini** - Google Gemini series
- Support for custom Base URL and model parameters

### 🚀 Interactive CLI Interface
- **Friendly Menu System** - No need to memorize complex commands
- **Real-time Configuration** - Dynamically adjust runtime parameters
- **Colorful Output** - Clear and beautiful interface (supports colorama)
- **Tool List Viewer** - View all available tools with one click

### 🛠️ Powerful Toolset
- `list_directory` - List directory contents
- `read_file` - Read text files
- `create_file` - Create or overwrite files
- `run_python` - Execute Python code
- `run_shell` - Execute Shell commands
- `task_complete` - Mark task as complete ⭐ New

### 🎯 Flexible Usage
- **Interactive Mode** - Menu-based operation, suitable for continuous tasks
- **Multi-turn Conversation Mode** - Continuous dialogue with complete history ⭐ New
- **Command-line Mode** - Quick execution of single tasks
- **Batch Mode** - Support for script automation
- **Persistent Configuration** - Custom settings saved permanently ⭐ New

## 📋 Prerequisites

- **Python 3.7+** (Recommended 3.9 or higher)
- **LLM API Key** - Choose based on model:
  - [DeepSeek API Key](https://platform.deepseek.com/) (default)
  - [OpenAI API Key](https://platform.openai.com/)
  - [Claude API Key](https://console.anthropic.com/)
  - [Gemini API Key](https://makersuite.google.com/app/apikey)

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd deepseek-react-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies**:
- `requests` - HTTP request library for calling DeepSeek API
- `python-dotenv` - Environment variable management
- `colorama` - Colorful terminal output (optional but recommended)

### 3. Configure API Key

Copy the `.env.example` file and rename it to `.env`, then add your real API key:

```bash
# Copy the example file
cp .env.example .env

# Edit the .env file, replace your_api_key_here with your actual key
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

**⚠️ Security Notice**:
- The `.env` file contains your private API key and is configured in `.gitignore` to prevent it from being committed to Git
- Do not share the `.env` file with others or upload it to public repositories
- Only the `.env.example` file will be committed to the repository as a configuration template

Or set the environment variable in the command line:

**Windows (PowerShell)**:
```powershell
$env:DEEPSEEK_API_KEY="your_api_key_here"
```

**Linux/macOS**:
```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

## 🚀 Quick Start

### Interactive Mode (Recommended)

Run the program directly to enter the friendly menu interface:

```bash
python main.py
```

You will see:

```
======================================================================
              DeepSeek ReAct Agent
======================================================================
Welcome to the DeepSeek-powered ReAct Agent System!

Main Menu:
  1. Execute New Task
  2. Multi-turn Conversation Mode
  3. View Available Tools
  4. Configuration Settings
  5. Exit Program

Please select an option (1-5):
```

### Command-line Mode (Quick Execution)

Execute tasks directly from the command line:

```bash
# Basic usage
python main.py "Create a hello.py file that prints hello world"

# Show detailed steps
python main.py "Calculate 123 + 456" --show-steps

# Custom configuration
python main.py "Your task" --max-steps 50 --temperature 0.5
```

## 📚 Usage Examples

### Example 1: File Operations

```bash
python main.py "Create a file named notes.txt with today's date"
```

### Example 2: Math Calculation

```bash
python main.py "Calculate the result of (100 + 200) * 3" --show-steps
```

### Example 3: Code Execution

```bash
python main.py "Use Python to generate 10 random numbers and save them to random.txt"
```

### Example 4: Complex Task

```bash
python main.py "Create a sort folder with 10 sorting algorithm implementations in both C++ and Python"
```

### Example 5: Multi-turn Conversation ⭐ New

```bash
python main.py
# Select option 2: Multi-turn Conversation Mode
# Conversation 1: "Create a test.py file"
# Conversation 2: "Write a function to print Hello in that file"
# Conversation 3: "Run that file"
# The agent will remember the context of test.py
```

## ⚙️ Command-line Arguments

```
python main.py [task] [options]

Positional Arguments:
  task                  Task description to execute (optional)

Optional Arguments:
  -h, --help           Show help message
  --api-key KEY        DeepSeek API key
  --model MODEL        Model name (default: deepseek-chat)
  --max-steps N        Maximum steps (default: 100) ⭐ Updated
  --temperature T      Temperature 0.0-2.0 (default: 0.7) ⭐ Updated
  --show-steps         Show execution steps
  --interactive        Force interactive mode
```

**Note**: Default values can be permanently modified via `config.json`

## 🎨 Interactive Menu Features

### 1️⃣ Execute New Task
Enter a task description, and the agent will automatically execute and display results. Each execution is a fresh conversation.

### 2️⃣ Multi-turn Conversation Mode ⭐ New
Enter continuous conversation mode where the agent remembers all conversation history and tool execution results:
- Type `exit` to quit conversation mode
- Type `reset` to clear conversation history
- The agent remembers file names, variables, and other context information

### 3️⃣ View Tool List
View all available tools and their function descriptions.

### 4️⃣ Configuration Settings ⭐ Enhanced
Dynamically adjust runtime parameters and optionally save permanently:
- **Max Steps** (max_steps): 1-200 (default: 100)
- **Temperature** (temperature): 0.0-2.0 (default: 0.7)
- **Show Steps** (show_steps): Yes/No

After modification, you can choose to save to `config.json`, which will be automatically loaded on next startup.

### 5️⃣ Exit Program
Safely exit the application.

## ⚙️ Configuration Management

### Default Configuration
- **Max Steps**: 100
- **Temperature**: 0.7
- **Show Steps**: No

### Persistent Configuration
1. Start the program and select "Configuration Settings"
2. Modify parameters as prompted
3. Choose `y` to save as permanent configuration
4. Configuration is saved in the `config.json` file

Configuration file example (`config.json.example`):
```json
{
  "model": "deepseek-chat",
  "max_steps": 100,
  "temperature": 0.7,
  "show_steps": false
}
```

**Tip**: `config.json` is added to `.gitignore` and will not be committed to git

## 🛡️ Error Handling

The program gracefully handles various errors:

- ✅ Missing API Key - Clear error messages
- ✅ API Call Failures - Display error details
- ✅ Invalid Input - Input validation and prompts
- ✅ Keyboard Interrupt - Exit anytime with Ctrl+C
- ✅ File Operation Errors - Friendly error messages

## 📖 More Documentation

- **[README_CLI.md](README_CLI.md)** - Complete Interactive CLI Guide
- **[CLI_USAGE_EXAMPLES.md](CLI_USAGE_EXAMPLES.md)** - Detailed Usage Examples
- **[CHANGELOG.md](CHANGELOG.md)** - Version Changelog
- **[INSTALL_COLORAMA.md](INSTALL_COLORAMA.md)** - Colorama Installation Guide

## 💡 Tips and Tricks

1. **Continuous Tasks** - Use interactive mode to avoid repeatedly starting the program
2. **Debug Tasks** - Use `--show-steps` to view detailed execution process
3. **Experimental Tasks** - Increase temperature value for more creative results
4. **Complex Tasks** - Increase max-steps to allow more reasoning steps (default is 100)
5. **Quick Testing** - Command-line mode is suitable for scripts and automation

## ❓ FAQ

**Q: How do I get a DeepSeek API key?**
A: Visit [DeepSeek Platform](https://platform.deepseek.com/) to register and obtain an API key.

**Q: How do I exit interactive mode?**
A: Select menu option 4, or press Ctrl+C.

**Q: Are configurations saved?**
A: Yes! You can now save configurations permanently. Select "Configuration Settings" in the menu, modify parameters, and choose to save. The settings will persist across restarts.

**Q: Is colorama required?**
A: No, the program works without it, just without colorful output.

**Q: Why does the task show "Reached step limit but not completed"?**
A: The task is too complex and requires more steps. You can increase the maximum steps via the `--max-steps` parameter or in the configuration settings in interactive mode (default is now 100).

## 🔄 Project Structure

```
deepseek-react-agent/
├── main.py                 # Main program entry (Interactive CLI)
├── deepseek_agent/         # Core agent package
│   ├── __init__.py        # Package initialization
│   ├── agent.py           # ReactAgent implementation
│   ├── client.py          # DeepSeek API client
│   └── tools.py           # Toolset definitions
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable configuration template
├── .env                    # Your private configuration (create yourself, not committed)
├── config.json.example     # Configuration file example
├── .gitignore             # Git ignore rules
└── README.md              # Project documentation
```

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- [DeepSeek](https://www.deepseek.com/) - Providing powerful AI models
- [Colorama](https://github.com/tartley/colorama) - Cross-platform colorful terminal output

---

**Start Learning AI Agents!** 🚀

