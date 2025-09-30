# Your First AI Agent Project

<div align="center">

**Intelligent Code Agent Based on Multiple LLM APIs**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) | **English**

</div>

## 📖 Project Overview

If you're just starting to learn about AI Agents and don't know where to begin, start with this project to learn or develop your own Agent applications.

This project provides all new AI Agent developers with an extremely low learning curve yet powerful **Code Agent**, based on the ReAct (Reasoning + Acting) architecture, supporting multiple large language models (DeepSeek, OpenAI, Claude, Gemini) for reasoning, and focused on software development and code-related tasks. The agent can:

- 📝 **Code Editing** - Precisely edit specific file lines with insert/replace/delete ⭐ New
- 🔍 **Code Search** - Regex search with context display ⭐ New
- 🧪 **Test Execution** - Run pytest/unittest test suites ⭐ New
- ✨ **Code Linting** - Run pylint/flake8/mypy/black linting tools ⭐ New
- 📁 **File Operations** - Create, read (with line ranges), list files and directories (with recursive filtering)
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

### 🛠️ Powerful Code Agent Toolset
**Code Editing Tools** ⭐ New
- `edit_file` - Precisely edit specific file lines (insert/replace/delete)
- `search_in_file` - Regex search with context display

**Testing and Linting Tools** ⭐ New
- `run_tests` - Run pytest/unittest test suites
- `run_linter` - Run pylint/flake8/mypy/black code linters

**File Operation Tools** ⭐ Enhanced
- `list_directory` - List directory contents (with recursive and type filtering)
- `read_file` - Read text files (with line number ranges)
- `create_file` - Create or overwrite files

**Code Execution Tools**
- `run_python` - Execute Python code
- `run_shell` - Execute Shell commands
- `task_complete` - Mark task as complete

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
- `requests` - HTTP request library for calling LLM API
- `python-dotenv` - Environment variable management
- `colorama` - Colorful terminal output (optional but recommended)
- `google-generativeai` - Google Gemini official SDK

### 3. Configure API Key

Copy the `.env.example` file and rename it to `.env`, then add your real API key:

```bash
# Copy the example file
cp .env.example .env

# Edit the .env file, configure the corresponding key based on the model you're using
# DeepSeek (default)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# OpenAI (optional)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Claude (optional)
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx

# Gemini (optional)
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
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
# Basic usage (using default DeepSeek)
python main.py "Create a hello.py file that prints hello world"

# Use OpenAI
python main.py "Your task" --provider openai --model gpt-4

# Use Claude
python main.py "Your task" --provider claude --model claude-3-5-sonnet-20241022

# Use Gemini
python main.py "Your task" --provider gemini --model gemini-1.5-flash

# Show detailed steps
python main.py "Calculate 123 + 456" --show-steps

# Custom configuration
python main.py "Your task" --max-steps 50 --temperature 0.5
```

## 📚 Usage Examples

### Example 1: Code Editing ⭐ New Feature
```bash
# Insert code at a specific line
python main.py "Insert a print statement at line 10 in test.py"

# Replace code in a line range
python main.py "Replace lines 5-8 in main.py with a new function implementation"

# Search and modify code
python main.py "Search for all code containing 'TODO' in the project and list them"
```

### Example 2: Testing and Code Linting ⭐ New Feature
```bash
# Run tests
python main.py "Run all test cases in the tests directory"

# Code linting
python main.py "Check code quality in the src directory with flake8"

# Format checking
python main.py "Check if main.py conforms to black code style"
```

### Example 3: File Operations (Enhanced)
```bash
# Read specific line range
python main.py "Read lines 10-20 of config.py"

# Recursively list Python files
python main.py "List all .py files in the project"

# Create file
python main.py "Create a file named notes.txt with today's date"
```

### Example 4: Math Calculation

```bash
python main.py "Calculate the result of (100 + 200) * 3" --show-steps
```

### Example 5: Code Execution

```bash
python main.py "Use Python to generate 10 random numbers and save them to random.txt"
```

### Example 6: Complex Task

```bash
python main.py "Create a sort folder with 10 sorting algorithm implementations in both C++ and Python"
```

### Example 7: Multi-turn Conversation ⭐ New

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
  --api-key KEY        API key
  --provider PROVIDER  LLM provider (deepseek/openai/claude/gemini, default: deepseek) ⭐ New
  --model MODEL        Model name (default based on provider)
  --base-url URL       API base URL (optional, uses provider default) ⭐ New
  --max-steps N        Maximum steps (default: 100)
  --temperature T      Temperature 0.0-2.0 (default: 0.7)
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
- **LLM Provider** (provider): deepseek/openai/claude/gemini ⭐ New
- **Model Name** (model): Choose based on provider
- **Base URL** (base_url): API base URL ⭐ New
- **Max Steps** (max_steps): 1-200 (default: 100)
- **Temperature** (temperature): 0.0-2.0 (default: 0.7)
- **Show Steps** (show_steps): Yes/No

After modification, you can choose to save to `config.json`, which will be automatically loaded on next startup.

### 5️⃣ Exit Program
Safely exit the application.

## ⚙️ Configuration Management

### Default Configuration
- **LLM Provider**: deepseek
- **Model**: deepseek-chat
- **Base URL**: https://api.deepseek.com
- **Max Steps**: 100
- **Temperature**: 0.7
- **Show Steps**: No

### Persistent Configuration
1. Start the program and select "Configuration Settings"
2. Modify parameters as prompted (including switching model providers)
3. Choose `y` to save as permanent configuration
4. Configuration is saved in the `config.json` file

Configuration file example (`config.json.example`):
```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "max_steps": 100,
  "temperature": 0.7,
  "show_steps": false
}
```

**Note**:
- Gemini uses the official Google SDK and doesn't need `base_url` configuration
- Other providers can customize `base_url` as needed (e.g., using a proxy)

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

**Q: How do I get an API key?**
A: Visit the corresponding platform based on your chosen provider:
- [DeepSeek Platform](https://platform.deepseek.com/)
- [OpenAI Platform](https://platform.openai.com/)
- [Claude Console](https://console.anthropic.com/)
- [Gemini API Console](https://makersuite.google.com/)

**Q: How do I switch between different models?**
A: There are three ways:
1. Command line: `python main.py "task" --provider openai --model gpt-4`
2. Interactive mode: Select "Configuration Settings" to modify provider and model
3. Config file: Edit `config.json` to permanently change

**Q: How do I exit interactive mode?**
A: Select menu option 5, or press Ctrl+C.

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

