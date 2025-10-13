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

### 🎯 Core Capabilities ⭐ v1.2.0 New
- 📋 **Task Planning** - Generate structured plans before execution, reduce ineffective operations by 30-50% (v1.1.0)
- 🧠 **Code Analysis** - Parse AST, extract function signatures, analyze dependencies (v1.1.0)
- 🗜️ **Context Compression** - Auto-compress conversation history, support long conversations without token overflow (v1.1.0)
- 🔌 **MCP Protocol Support** - Integrate any MCP tools, unlimited extensibility (v1.2.0) ⭐ New

### 🛠️ Tool Capabilities
- 📝 **Code Editing** - Precisely edit specific file lines with insert/replace/delete
- 🔍 **Code Search** - Regex search with context display
- 🧪 **Test Execution** - Run pytest/unittest test suites
- ✨ **Code Linting** - Run pylint/flake8/mypy/black linting tools
- 📁 **File Operations** - Create, read (with line ranges), list files and directories (with recursive filtering)
- 🐍 **Python Execution** - Run Python code and scripts
- 💻 **Shell Commands** - Execute system commands
- 🎯 **Task Completion** - Intelligently mark task completion status
- 🎨 **Interactive Interface** - User-friendly menu-based operation experience

## ✨ Key Features

### 🎯 v1.1.0 New Core Features
#### 📋 Task Planner
- **Smart Plan Generation** - Auto-generate 3-8 step structured plans before task execution
- **Real-time Progress Tracking** - Mark completed steps with clear execution progress display
- **30-50% Efficiency Boost** - Reduce ineffective tool calls and improve task success rate
- **Auto Fallback** - Automatically switch to regular mode if plan generation fails

#### 🧠 Code Analysis Tools
- **parse_ast** - Parse Python file AST, extract functions, classes, imports structure
- **get_function_signature** - Get complete function signature with type annotations
- **find_dependencies** - Analyze file dependencies (stdlib, third-party, local modules)
- **get_code_metrics** - Count code lines, functions, classes metrics

#### 🗜️ Context Compressor
- **Auto Compression** - Auto-compress history every 5 turns, keep recent 3 turns intact
- **Smart Summary** - Extract key info (file paths, tool calls, errors, completed tasks)
- **Save Tokens** - Reduce 20-30% token consumption, support longer conversations
- **Seamless Integration** - Fully automatic, no manual intervention needed

#### 🔌 MCP Protocol Integration (Model Context Protocol) ⭐ v1.2.0 New
- **Zero-Code Extension** - Integrate any MCP tools via config file, no code changes needed
- **Pre-installed Playwright** - Built-in browser automation (navigate, screenshot, click, fill forms)
- **Pre-installed Context7** - Intelligent context management and semantic search
- **Unified Tool Interface** - MCP tools auto-wrapped as standard Tool objects
- **Lifecycle Management** - Auto-start and stop MCP server processes
- **Common MCP Support** - Playwright, Context7, Filesystem, SQLite, etc.
- **Detailed Documentation** - See [MCP_GUIDE.md](MCP_GUIDE.md) for complete integration guide

### 🤖 Multi-Model Support
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

**MCP Tools** ⭐ v1.2.0 New
- `mcp_playwright_*` - Browser automation tools (navigate, screenshot, click, forms)
- `mcp_context7_*` - Intelligent context management tools (store, retrieve, search)
- Support dynamic loading of any MCP tools

**Code Analysis Tools** (v1.1.0)
- `parse_ast` - Parse Python file AST structure
- `get_function_signature` - Extract function signature and types
- `find_dependencies` - Analyze file dependencies
- `get_code_metrics` - Get code metrics

**Code Editing Tools**
- `edit_file` - Precisely edit specific file lines (insert/replace/delete)
- `search_in_file` - Regex search with context display

**Testing and Linting Tools**
- `run_tests` - Run pytest/unittest test suites
- `run_linter` - Run pylint/flake8/mypy/black code linters

**File Operation Tools**
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
cd dm-agent
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

### 🌐 Web UI Mode (Recommended) ⭐ v1.3.0+

The modern web interface delivers real-time conversations, visual settings, and tool management.

#### Install frontend dependencies (first time only)

```bash
# enter the frontend folder
cd frontend

# requires Node.js 16+
npm install
```

#### Launch the system

**1. Start the backend (project root):**
```bash
python app.py
```

**2. Start the frontend (new terminal, `frontend/` directory):**
```bash
cd frontend
npm run dev
```

**3. Open the interface:**
Visit **http://localhost:3000** in your browser.


#### 🖥️ UI Highlights (actively refined)
- **Wide two-column layout** – scales up to 1920px+ so prompts/plans live on the left and live status/logs on the right.
- **Scroll-inside cards** – execution plan, status, and logs keep fixed heights and scroll internally, keeping the page calm even for long tasks.
- **Collapsible long replies** – messages longer than ~600 characters or 12 lines collapse automatically; click “Expand all / Collapse” to toggle readability.
- **Gradients & breathing cues** – subtle gradients and animated status pills make it easy to spot the agent’s progress at a glance.

---

### Interactive Mode (Recommended)

Run the program directly to enter the friendly menu interface:

```bash
python main.py
```

You will see:

```
======================================================================
              DM-Agent System
======================================================================
Welcome to the Multi-Model ReAct Agent System!

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

#### Task Planner Example
```bash
python main.py "Create a complete calculator program with add, subtract, multiply, divide functions and tests"
```

You will see:
```
📋 Generated Execution Plan:
Plan Progress: 0/5 steps completed

○ Step 1: create_file - Create calculator main program file
○ Step 2: edit_file - Add calculation functions
○ Step 3: create_file - Create test file
○ Step 4: run_tests - Run tests for verification
○ Step 5: task_complete - Complete task
```

#### Code Analysis Tools Example
```bash
# Analyze file structure
python main.py "Analyze the code structure of main.py and list all functions and classes"

# Extract function signature
python main.py "Get the complete signature of the calculate function in calculator.py"

# Analyze dependencies
python main.py "Analyze what third-party libraries main.py depends on"

# Get code metrics
python main.py "Count the number of code lines in all Python files in the src directory"
```

#### Context Compression Example
In multi-turn conversation mode, auto-compress every 5 turns:
```
🗜️ Compressing conversation history to save tokens...
   Compression ratio: 62.5%, saved 10 messages
```

### Example 0.5: MCP Tools Usage ⭐ v1.2.0

#### Playwright MCP Example (Browser Automation)
```bash
# Open webpage and take screenshot
python main.py "Open https://www.example.com and save screenshot as example.png"

# Automate form filling
python main.py "Open https://example.com/login, enter 'testuser' in username field, 'password123' in password field, then click login"

# Extract webpage data
python main.py "Visit https://news.ycombinator.com and extract the top 10 news headlines"
```

#### Context7 MCP Example (Context Management)
```bash
# Store context
python main.py "Store the current project architecture information in Context7"

# Semantic search
python main.py "Search for database-related contexts in Context7"

# Related context
python main.py "Get historical contexts related to the current task"
```

#### Integrate New MCP Tools
Only 3 steps, no code needed:
1. Edit `mcp_config.json` to add configuration
2. Restart the system
3. Tools automatically available

See: [MCP_GUIDE.md](MCP_GUIDE.md)

### Example 1: Code Editing
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

## 💡 Tips and Tricks

1. **Continuous Tasks** - Use interactive mode to avoid repeatedly starting the program
2. **Debug Tasks** - Use `--show-steps` to view detailed execution process
3. **Experimental Tasks** - Increase temperature value for more creative results
4. **Complex Tasks** - Increase max-steps to allow more reasoning steps (default is 100)
5. **Quick Testing** - Command-line mode is suitable for scripts and automation


## 🔄 Project Structure

```
dm-code-agent/
├── main.py                         # Main program entry (Interactive CLI)
├── check_mcp_env.py                # MCP environment check tool (v1.2.0)
├── dm_agent/                       # Core agent package
│   ├── __init__.py                # Package initialization and public API
│   ├── core/                      # Core Agent implementation
│   │   ├── __init__.py
│   │   ├── agent.py              # ReactAgent core logic
│   │   └── planner.py            # Task planner (v1.1.0)
│   ├── clients/                   # LLM clients
│   │   ├── __init__.py
│   │   ├── base_client.py        # Base client class
│   │   ├── deepseek_client.py    # DeepSeek client
│   │   ├── openai_client.py      # OpenAI client
│   │   ├── claude_client.py      # Claude client
│   │   ├── gemini_client.py      # Gemini client
│   │   └── llm_factory.py        # Client factory
│   ├── mcp/                       # MCP integration (v1.2.0)
│   │   ├── __init__.py
│   │   ├── client.py             # MCP client
│   │   ├── config.py             # MCP configuration management
│   │   └── manager.py            # MCP manager
│   ├── memory/                    # Memory and context management (v1.1.0)
│   │   ├── __init__.py
│   │   └── context_compressor.py # Context compressor
│   ├── tools/                     # Toolset
│   │   ├── __init__.py
│   │   ├── base.py               # Tool base class
│   │   ├── file_tools.py         # File operation tools
│   │   ├── code_analysis_tools.py # Code analysis tools (v1.1.0)
│   │   └── execution_tools.py    # Code execution tools
│   └── prompts/                   # Prompt management
│       ├── __init__.py
│       ├── system_prompts.py     # Prompt building functions
│       └── code_agent_prompt.md  # Prompt template
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable configuration template
├── config.json.example            # Configuration file example
├── mcp_config.json.example        # MCP configuration example (v1.2.0)
├── .gitignore                     # Git ignore rules
├── MCP_GUIDE.md                   # MCP integration guide (v1.2.0)
├── README.md                      # Chinese documentation
└── README_EN.md                   # English documentation
```

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

This project is licensed under the MIT License.

**Start Learning AI Agents!** 🚀
