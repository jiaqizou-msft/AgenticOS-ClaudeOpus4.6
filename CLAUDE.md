# AgenticOS — Project Memory

## Overview
AgenticOS is a modular framework for turning Windows into an AI-navigable operating system.
Users chat from a CLI and an AI agent performs real-time OS interactions — clicking, typing,
navigating apps, running commands — with full screen understanding and precise action execution.

## Architecture
```
CLI Chat (rich) → Agent Orchestrator (ReAct loop) → Screen Capture + Grounding → LLM → Action Executors
                                                                                          ↕
                                                                                     MCP Server (extensible tools)
```

### Module Structure
- `src/agenticos/agent/` — Core agent logic (base interface, navigator, planner)
- `src/agenticos/grounding/` — UI element detection (UIA accessibility, vision, OCR)
- `src/agenticos/actions/` — Action execution (keyboard, mouse, shell, window management)
- `src/agenticos/observation/` — Screen capture and GIF recording
- `src/agenticos/mcp/` — MCP server exposing all capabilities as tools
- `src/agenticos/evaluation/` — Benchmark metrics and task definitions
- `src/agenticos/utils/` — Configuration and shared utilities
- `src/agenticos/cli.py` — Entry point CLI chat interface

## Key Commands
```bash
# Install
pip install -e ".[dev]"

# Run CLI
agenticos

# Run tests
pytest

# Run benchmarks
pytest tests/benchmarks/ --benchmark-json=benchmark.json

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/
```

## Code Style
- Python 3.10+, type annotations on all public functions
- Use `pydantic` for data models and configuration
- Use `async/await` for I/O-bound operations
- Use `rich` for terminal output
- 100 char line length (ruff)
- Docstrings: Google style
- Tests: pytest with fixtures, benchmarks via pytest-benchmark

## Key Design Decisions
1. **Hybrid grounding**: UIA accessibility tree first (fast, structured), vision LLM fallback (universal)
2. **ReAct loop**: Observe → Think → Act → Repeat until task complete or max steps
3. **MCP extensibility**: Every capability is an MCP tool — pluggable by any MCP host
4. **Safety gate**: User confirmation before destructive actions (bypass with `--yes`)
5. **GIF recording**: Every agent session auto-records for debugging and demo generation
6. **Multi-LLM**: litellm for provider-agnostic LLM access (Claude, GPT, Ollama)

## Benchmarks
- Custom Windows benchmark suite: basic (15 tasks), intermediate (10), advanced (5)
- Metrics: success rate, step efficiency, time-to-complete, grounding accuracy
- Compared against: UFO² (30.5% WAA), Operator (20.8%), Navi (19.5%), human (74.5%)

## Dependencies
- Core: litellm, anthropic, mss, pywinauto, pyautogui, rich, mcp, pydantic
- Dev: pytest, pytest-benchmark, ruff, mypy
- Optional: rapidocr-onnxruntime (OCR), torch+transformers (vision models)
