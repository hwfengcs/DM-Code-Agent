# Your First AI Agent Project

<div align="center">

**Intelligent ReAct (Reasoning + Acting) Agent Based on DeepSeek API**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) | **English**

</div>

## 📖 Project Overview

If you're just starting to learn about AI Agents and don't know where to begin, start with this project to learn or develop your own Agent applications.

This project provides all new AI Agent developers with an extremely low learning curve yet fully functional **ReAct (Reasoning + Acting) Agent**, powered by DeepSeek's large language model for reasoning and local tool execution to complete various tasks. The agent can:

- 📁 **File Operations** - Create, read, and list files and directories
- 🐍 **Python Execution** - Run Python code and scripts
- 💻 **Shell Commands** - Execute system commands
- 🎯 **Task Completion** - Intelligently mark task completion status
- 🎨 **Interactive Interface** - User-friendly menu-based operation experience

## ✨ Key Features

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
- **Command-line Mode** - Quick execution of single tasks
- **Batch Mode** - Support for script automation

## 📋 Prerequisites

- **Python 3.7+** (Recommended 3.9 or higher)
- **DeepSeek API Key** - [Get API Key](https://platform.deepseek.com/)

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

Create a `.env` file and add your API key:

```bash
# .env file
DEEPSEEK_API_KEY=your_api_key_here
```

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
  2. View Available Tools
  3. Configuration Settings
  4. Exit Program

Please select an option (1-4):
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

## ⚙️ Command-line Arguments

```
python main.py [task] [options]

Positional Arguments:
  task                  Task description to execute (optional)

Optional Arguments:
  -h, --help           Show help message
  --api-key KEY        DeepSeek API key
  --model MODEL        Model name (default: deepseek-chat)
  --max-steps N        Maximum steps (default: 50)
  --temperature T      Temperature 0.0-2.0 (default: 0.0)
  --show-steps         Show execution steps
  --interactive        Force interactive mode
```

## 🎨 Interactive Menu Features

### 1️⃣ Execute New Task
Enter a task description, and the agent will automatically execute and display results.

### 2️⃣ View Tool List
View all available tools and their function descriptions.

### 3️⃣ Configuration Settings
Dynamically adjust runtime parameters:
- **Max Steps** (max_steps): 1-200
- **Temperature** (temperature): 0.0-2.0
- **Show Steps** (show_steps): Yes/No

### 4️⃣ Exit Program
Safely exit the application.

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
4. **Complex Tasks** - Increase max-steps to allow more reasoning steps (default is 50)
5. **Quick Testing** - Command-line mode is suitable for scripts and automation

## ❓ FAQ

**Q: How do I get a DeepSeek API key?**
A: Visit [DeepSeek Platform](https://platform.deepseek.com/) to register and obtain an API key.

**Q: How do I exit interactive mode?**
A: Select menu option 4, or press Ctrl+C.

**Q: Are configurations saved?**
A: Configurations are only valid for the current session and reset to defaults after restart.

**Q: Is colorama required?**
A: No, the program works without it, just without colorful output.

**Q: Why does the task show "Reached step limit but not completed"?**
A: The task is too complex and requires more steps. You can increase the maximum steps via the `--max-steps` parameter or in the configuration settings in interactive mode (default has been increased from 8 to 50).

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
├── .env                    # Environment variable configuration (create yourself)
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

