<div align="center">

# 🖥️ AgenticOS

**Turn Windows into an AI-Navigable Desktop via CLI Chat**

[![CI](https://github.com/jiaqizou/AgenticOS-ClaudeOpus4.6/actions/workflows/ci.yml/badge.svg)](https://github.com/jiaqizou/AgenticOS-ClaudeOpus4.6/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

*A modular Python framework for deep OS integration and intelligent desktop automation using multi-modal LLMs.*

</div>

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI / Chat Interface                     │
│                    (Rich + Click terminal)                    │
├─────────────────────────────────────────────────────────────┤
│                      Agent Layer                             │
│    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│    │  Navigator    │  │   Planner    │  │   ReAct Loop │     │
│    │  (LLM core)  │  │  (decompose) │  │   (observe→  │     │
│    │              │  │              │  │    think→act) │     │
│    └──────────────┘  └──────────────┘  └──────────────┘     │
├─────────────────────────────────────────────────────────────┤
│                   Grounding Layer                            │
│    ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│    │   UIA    │    │  Vision  │    │   OCR    │             │
│    │(pywinauto│    │  (VLM)   │    │(RapidOCR)│             │
│    │ a11y tree│    │          │    │          │             │
│    └──────────┘    └──────────┘    └──────────┘             │
├─────────────────────────────────────────────────────────────┤
│                    Action Layer                              │
│    ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────┐        │
│    │Keyboard│  │ Mouse  │  │ Shell  │  │ Window   │        │
│    │        │  │        │  │        │  │ Manager  │        │
│    └────────┘  └────────┘  └────────┘  └──────────┘        │
├─────────────────────────────────────────────────────────────┤
│                  Observation Layer                            │
│    ┌───────────────┐    ┌──────────────────┐                │
│    │  Screenshot   │    │  GIF Recorder    │                │
│    │  (mss)        │    │  (imageio)       │                │
│    └───────────────┘    └──────────────────┘                │
├─────────────────────────────────────────────────────────────┤
│               MCP Server (FastMCP)                           │
│    11 tools exposed for external LLM integration             │
└─────────────────────────────────────────────────────────────┘
```

## ✨ Features

- **🤖 Multi-LLM Support** — Claude, GPT-4o, Gemini, Ollama local models via `litellm`
- **🔍 Hybrid Screen Understanding** — UIA accessibility tree + VLM vision + OCR (three-layer fallback)
- **⌨️ Full Input Simulation** — Keyboard, mouse, shell commands, window management
- **🎬 GIF Session Recording** — Automatic recording of agent actions with annotations
- **🔌 MCP Server** — 11 tools exposed via Model Context Protocol for external integration
- **📊 Built-in Benchmarks** — 30 tasks across basic/intermediate/advanced categories
- **🛡️ Safety First** — Dangerous command blocklist, action confirmation, step limits

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/jiaqizou/AgenticOS-ClaudeOpus4.6.git
cd AgenticOS-ClaudeOpus4.6

# Install in development mode
pip install -e ".[dev]"

# Set your API key
set ANTHROPIC_API_KEY=your-key-here
```

### Usage

```bash
# Interactive chat mode
agenticos

# Single task mode
agenticos --task "Open Notepad and type Hello World"

# With a specific model
agenticos --model gpt-4o --task "Take a screenshot and save it"

# Skip action confirmations
agenticos --no-confirm --task "Open Calculator"

# Without GIF recording
agenticos --no-record --task "List files on desktop"
```

### MCP Server

```bash
# Run the MCP server (for integration with Claude Desktop, etc.)
python -m agenticos.mcp.server
```

## 📦 Project Structure

```
AgenticOS/
├── src/agenticos/
│   ├── __init__.py              # Package root (version)
│   ├── cli.py                   # Rich CLI chat interface
│   ├── utils/
│   │   ├── config.py            # Pydantic-settings configuration
│   │   └── exceptions.py        # Custom exception hierarchy
│   ├── observation/
│   │   ├── screenshot.py        # mss-based screen capture
│   │   └── recorder.py          # Threaded GIF recorder
│   ├── grounding/
│   │   ├── accessibility.py     # pywinauto UIA grounding
│   │   ├── visual.py            # VLM-based visual grounding
│   │   └── ocr.py               # RapidOCR text detection
│   ├── actions/
│   │   ├── keyboard.py          # Keyboard input executor
│   │   ├── mouse.py             # Mouse input executor
│   │   ├── shell.py             # Shell command executor
│   │   ├── window.py            # Window manager
│   │   └── compositor.py        # Action dispatch & retry (16 types)
│   ├── agent/
│   │   ├── base.py              # Base agent ABC & data classes
│   │   ├── navigator.py         # Core ReAct navigator agent
│   │   ├── planner.py           # LLM task decomposition
│   │   ├── state_validator.py   # Post-action state validation
│   │   ├── recovery.py          # Per-app recovery strategies
│   │   ├── step_memory.py       # Cached step patterns
│   │   ├── reinforcement.py     # Tabular Q-learning (RL)
│   │   └── human_teacher.py     # Learning from Demonstration (LfD)
│   ├── mcp/
│   │   └── server.py            # FastMCP server (11 tools)
│   └── evaluation/
│       ├── metrics.py           # Benchmark metrics & reporting
│       └── tasks.py             # 30 built-in benchmark tasks
├── scripts/
│   ├── run_demo_detached.py     # Live demo runner (4 demos)
│   ├── human_teach.py           # Human teaching CLI
│   ├── run_benchmark.py         # Benchmark runner
│   └── record_demo.py           # GIF demo recorder
├── recordings/
│   ├── demo1_settings.gif       # Demo 1 recording
│   ├── demo2_edge_video.gif     # Demo 2 recording
│   ├── demo4_file_explorer.gif  # Demo 4 recording
│   ├── rl_qtable.json           # Persistent Q-table
│   ├── step_memory.json         # Cached step patterns
│   └── teaching/                # Learned demonstration patterns
├── paper/                       # Academic paper (LaTeX)
├── tests/                       # Unit test suite
├── pyproject.toml               # Project config & dependencies
├── CLAUDE.md                    # Project memory for AI agents
└── README.md                    # This file
```

## 🎬 Live Demo Results

Real demos run on Windows 11 with GPT-4o (Azure OpenAI):

| Demo | Task | Steps | Time | Status | Iterations |
|------|------|-------|------|--------|------------|
| **Demo 1** | System Tray: Set brightness to 100% | 5 | 68s | ✅ SUCCESS | 1 |
| **Demo 2** | Edge: Play 4K YouTube video fullscreen | 9 | 138s | ✅ SUCCESS | 9 |
| **Demo 3** | Outlook email + Teams message | — | — | 🔄 In Progress | 2 |
| **Demo 4** | File Explorer: Create folder in Downloads | 15 | 220s | 🔄 In Progress | 3 |

### Key Innovations Discovered Through Iteration

- **UIA Slider Control** (Demo 1): Direct `RangeValuePattern.SetValue()` via UIA — 100% reliable vs. unreliable mouse drag
- **Content Verification** (Demo 2): Post-click window title check + RL negative reward for wrong content
- **Recovery-Aware Actions** (Demo 4): Auto-recovery (Escape) can sabotage in-progress operations like folder rename — solved with per-app recovery disabling
- **Done Verification** (Demo 4): Filesystem path check before accepting task completion — prevents false success

## 🧠 Learning Systems

### Reinforcement Learning
- **Algorithm**: Tabular Q-learning with TD update ($\alpha=0.15$, $\gamma=0.9$)
- **State**: Hash of UI context (window title + element count + top elements)
- **Rewards**: +2.0 (done success), +0.3 (state changed), -0.7 (drift), -1.2 (wrong content)
- **Persistence**: Q-table saved to `recordings/rl_qtable.json` across sessions

### Human Teaching (Learning from Demonstration)
- **11 teaching topics** defined (slider, navigation, folder creation, email, etc.)
- **1 pattern learned** so far: "Creating a new folder in File Explorer"
- **Workflow**: Record human demo → extract trajectory pattern → inject into LLM context
- **CLI**: `python scripts/human_teach.py --topic <topic_id>`

## 📊 Benchmark Results

AgenticOS includes a comprehensive benchmark suite with 30 tasks:

| Category       | Tasks | Description                                        |
|---------------|-------|----------------------------------------------------|
| **Basic**      | 15    | Single-app operations (Notepad, Calculator, Explorer) |
| **Intermediate** | 10 | Multi-step workflows, settings, clipboard            |
| **Advanced**   | 5     | Multi-app coordination, error recovery               |

### Comparison with Existing Systems

| System         | Architecture     | Grounding        | Success Rate | Open Source |
|---------------|------------------|------------------|-------------|-------------|
| **AgenticOS** | Modular ReAct    | UIA+Vision+OCR  | TBD         | ✅           |
| UFO²           | Dual-agent       | UIA + Vision     | 30.5%*      | ✅           |
| Operator       | CUA              | Vision only      | 20.8%*      | ❌           |
| Navi           | Foundation model | Vision only      | 19.5%*      | ❌           |
| Claude CU      | ReAct            | Vision only      | —           | ❌           |

*Results from OSWorld benchmark (Ubuntu). Windows results may differ.

## 🔧 Configuration

AgenticOS uses environment variables or `.env` files:

| Variable              | Default                          | Description                  |
|-----------------------|----------------------------------|------------------------------|
| `ANTHROPIC_API_KEY`   | —                                | Anthropic API key            |
| `OPENAI_API_KEY`      | —                                | OpenAI API key               |
| `AGENTICOS_MODEL`     | `claude-sonnet-4-20250514`   | LLM model to use             |
| `AGENTICOS_MAX_STEPS` | `15`                             | Max steps per task           |
| `AGENTICOS_GROUNDING` | `hybrid`                         | Grounding mode               |
| `AGENTICOS_CONFIRM`   | `true`                           | Confirm before actions       |

## 🧪 Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agenticos --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/agenticos/

# Format
ruff format src/ tests/
```

## 📄 Academic Paper

See [paper/](paper/) for the full LaTeX source of our paper:

> **AgenticOS: A Modular Framework for Deep OS Integration and Intelligent Desktop Automation**

The paper presents our architecture, compares against existing systems (UFO², Operator, Claude Computer Use, OmniParser), and evaluates performance on our 30-task benchmark suite.

## 📜 License

[MIT License](LICENSE) — see LICENSE file for details.

## 🙏 Acknowledgments

- [UFO](https://github.com/microsoft/UFO) — Microsoft's UI-Focused Agent for Windows
- [OmniParser](https://github.com/microsoft/OmniParser) — Screen Parsing Toolkit
- [litellm](https://github.com/BerriAI/litellm) — Multi-LLM provider proxy
- [pywinauto](https://github.com/pywinauto/pywinauto) — Windows UI Automation
- [FastMCP](https://github.com/jlowin/fastmcp) — Model Context Protocol SDK
