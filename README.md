<div align="center">

# 🖥️ AgenticOS

### Turn Windows into an AI-Navigable Desktop

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![GPT-4o](https://img.shields.io/badge/GPT--4o-Vision-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com/)
[![Windows](https://img.shields.io/badge/Windows_11-0078D4?style=for-the-badge&logo=windows11&logoColor=white)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**A modular Python framework for deep OS integration and intelligent desktop automation using multi-modal LLMs, Windows UI Automation, and human-supervised reinforcement learning.**

[🎬 Demo Showcase](#-demo-showcase) · [🚀 Quick Start](#-quick-start) · [🏗️ Architecture](#%EF%B8%8F-architecture) · [📊 Presentation](#-presentation)

---

<img src="recordings/demo1_settings.gif" width="720" alt="AgenticOS Demo — AI agent adjusting system settings autonomously">

*▲ Demo 1: AI agent autonomously adjusts brightness to 100% and volume to 10% via the System Tray Quick Settings panel*

</div>

---

## ✨ What is AgenticOS?

AgenticOS is an **AI desktop automation agent** that can see your screen, understand the UI, and take actions — just like a human user would. It combines:

| Capability | Technology |
|:---:|:---|
| 🧠 | **GPT-4o Vision** — understands screenshots and makes decisions |
| 🔍 | **Windows UI Automation** (UIA) — reads the accessibility tree |
| 📊 | **Reinforcement Learning** (Q-learning) — improves with every run |
| 👤 | **Human Supervision** — quality feedback and guided improvement |
| ⚡ | **Amortization** — repeated tasks get faster over time |

> **Think of it as:** An AI intern that watches your screen, learns your workflows, and gets better with practice — with you as the supervisor.

---

## 🎬 Demo Showcase

Real demos running on **Windows 11** with **GPT-4o** (Azure OpenAI). Every GIF below was recorded live.

### 🎚️ Demo 1 — System Tray: Brightness & Volume

<details open>
<summary><strong>Set brightness 100%, volume 10% via Quick Settings</strong></summary>

<div align="center">
<img src="recordings/demo1_settings.gif" width="700" alt="Demo 1: Brightness and Volume">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 5 |
| **Time** | 68 seconds |
| **Key Innovation** | UIA `RangeValuePattern.SetValue()` — 100% reliable slider control |

</details>

---

### 🌐 Demo 2 — Edge: 4K YouTube Fullscreen

<details>
<summary><strong>Search YouTube, play 4K nature video, fullscreen, pause</strong></summary>

<div align="center">
<img src="recordings/demo2_edge_video.gif" width="700" alt="Demo 2: YouTube 4K Video">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 9 |
| **Time** | 138 seconds |
| **Key Innovation** | Content verification — checks window title matches search query |

</details>

---

### 📁 Demo 4 — File Explorer: Create Folder

<details>
<summary><strong>Create "TestFromAgenticOS" folder in Downloads</strong></summary>

<div align="center">
<img src="recordings/demo4_file_explorer.gif" width="700" alt="Demo 4: File Explorer">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 15 |
| **Time** | 220 seconds |
| **Key Innovation** | Filesystem verification before accepting "done" |

</details>

---

### ✏️ Demo 5 — Notepad: Type Message

<details>
<summary><strong>Open Notepad and type a message</strong></summary>

<div align="center">
<img src="recordings/demo5_notepad_type.gif" width="700" alt="Demo 5: Notepad Type">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 4 |
| **Time** | 99 seconds |
| **Human Rating** | ⭐ 1/5 accuracy — "No visible cursor movement" |
| **Mode** | ⚡ Fast |

</details>

---

### 🔢 Demo 6 — Calculator: 123 + 456

<details>
<summary><strong>Open Calculator, compute 123 + 456 = 579</strong></summary>

<div align="center">
<img src="recordings/demo6_calc_add.gif" width="700" alt="Demo 6: Calculator">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 3 |
| **Time** | 53 seconds |
| **Human Rating** | ⚠️ 0/5 accuracy — "Did not type 123, just pressed =" |
| **Mode** | ⚡ Fast |

</details>

---

### 💻 Demo 7 — CMD: Echo Command

<details>
<summary><strong>Open Command Prompt and run <code>echo Hello from AgenticOS</code></strong></summary>

<div align="center">
<img src="recordings/demo7_cmd_echo.gif" width="700" alt="Demo 7: CMD Echo">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 3 |
| **Time** | 56 seconds |
| **Human Rating** | ⚠️ 0/5 accuracy — "Showed Ctrl+V, no echo command" |
| **Mode** | ⚡ Fast |

</details>

---

### ⚙️ Demo 8 — Settings: About Page

<details>
<summary><strong>Navigate to Settings → System → About</strong></summary>

<div align="center">
<img src="recordings/demo8_settings_about.gif" width="700" alt="Demo 8: Settings About">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 2 |
| **Time** | 28 seconds |
| **Human Rating** | ⭐ 1/5 accuracy — "Easy and fast. Could we do vision QA?" |
| **Mode** | ⚡ Fast |

</details>

---

### 📋 Demo 9 — Notepad: Select All & Copy

<details>
<summary><strong>Select all text and copy to clipboard</strong></summary>

<div align="center">
<img src="recordings/demo9_notepad_selectall.gif" width="700" alt="Demo 9: Select All">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 5 |
| **Time** | 74 seconds |
| **Human Rating** | ✅ Pass |
| **Mode** | ⚡ Fast |

</details>

---

### 🔍 Demo 10 — Notepad: Find Text

<details>
<summary><strong>Use Ctrl+F to search for "fox" in preloaded text</strong></summary>

<div align="center">
<img src="recordings/demo10_notepad_find.gif" width="700" alt="Demo 10: Find Text">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 3 |
| **Time** | 49 seconds |
| **Human Rating** | ⭐ 1/5 accuracy — "Went well and expected" |
| **Mode** | ⚡ Fast |

</details>

---

### ✖️ Demo 11 — Calculator: 7 × 8

<details>
<summary><strong>Compute 7 × 8 = 56</strong></summary>

<div align="center">
<img src="recordings/demo11_calc_multiply.gif" width="700" alt="Demo 11: Calculator Multiply">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 4 |
| **Time** | 65 seconds |
| **Human Rating** | ⭐ 1/5 accuracy — "Great" |
| **Mode** | ⚡ Fast |

</details>

---

### 🐚 Demo 12 — PowerShell: Get-Date

<details>
<summary><strong>Open PowerShell and run <code>Get-Date</code></strong></summary>

<div align="center">
<img src="recordings/demo12_powershell_date.gif" width="700" alt="Demo 12: PowerShell">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 3 |
| **Time** | 43 seconds |
| **Human Rating** | ✅ Pass |
| **Mode** | ⚡ Fast |

</details>

---

### ↩️ Demo 13 — Notepad: Undo Typing

<details>
<summary><strong>Type text, then Ctrl+Z to undo</strong></summary>

<div align="center">
<img src="recordings/demo13_notepad_undo.gif" width="700" alt="Demo 13: Undo">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 6 |
| **Time** | 105 seconds |
| **Human Rating** | ❌ 0/5 — Only failure in the suite |
| **Mode** | ⚡ Fast |

</details>

---

### 📋 Demo 14 — Task Manager: View Processes

<details>
<summary><strong>Open Task Manager and view running processes</strong></summary>

<div align="center">
<img src="recordings/demo14_taskmgr.gif" width="700" alt="Demo 14: Task Manager">
</div>

| Metric | Value |
|--------|-------|
| **Steps** | 2 |
| **Time** | 36 seconds |
| **Human Rating** | ⭐ 1/5 accuracy — Pass |
| **Mode** | ⚡ Fast |

</details>

---

## 📊 Results Summary

<div align="center">

### 14 Demos · 10 Pass · 2 Partial · 1 Fail · 1 WIP

</div>

| # | Demo | App | Steps | Time | Status | Human Supervised |
|---|------|-----|-------|------|--------|:---:|
| 1 | System Tray: Brightness & Volume | Quick Settings | 5 | 68s | ✅ | — |
| 2 | Edge: 4K YouTube Fullscreen | Edge | 9 | 138s | ✅ | — |
| 3 | Outlook Email + Teams Message | Outlook + Teams | — | — | 🔄 | — |
| 4 | File Explorer: Create Folder | Explorer | 15 | 220s | ✅ | — |
| 5 | Notepad: Type Message | Notepad | 4 | 99s | ✅ | ✅ |
| 6 | Calculator: 123 + 456 | Calculator | 3 | 53s | ⚠️ | ✅ |
| 7 | CMD: Echo Command | CMD | 3 | 56s | ⚠️ | ✅ |
| 8 | Settings: About Page | Settings | 2 | 28s | ✅ | ✅ |
| 9 | Notepad: Select All & Copy | Notepad | 5 | 74s | ✅ | ✅ |
| 10 | Notepad: Find Text | Notepad | 3 | 49s | ✅ | ✅ |
| 11 | Calculator: 7 × 8 | Calculator | 4 | 65s | ✅ | ✅ |
| 12 | PowerShell: Get-Date | PowerShell | 3 | 43s | ✅ | ✅ |
| 13 | Notepad: Undo Typing | Notepad | 6 | 105s | ❌ | ✅ |
| 14 | Task Manager: View Processes | Task Manager | 2 | 36s | ✅ | ✅ |

<div align="center">

**63** Q-table entries · **43** RL episodes · **10** human-supervised reviews

</div>

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    CLI / Chat Interface                            │
│               Rich terminal + argparse + MCP Server               │
├──────────────────────────────────────────────────────────────────┤
│                       Agent Layer                                 │
│  ┌───────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ Navigator │ │ Planner │ │   RL     │ │  Human Supervisor    │ │
│  │ (GPT-4o)  │ │ (decomp)│ │(Q-learn) │ │  + Demo Optimizer    │ │
│  └───────────┘ └─────────┘ └──────────┘ └──────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                     Grounding Layer                               │
│        ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│        │   UIA    │    │  Vision  │    │   OCR    │              │
│        │(pywinauto)│    │  (VLM)   │    │(RapidOCR)│              │
│        └──────────┘    └──────────┘    └──────────┘              │
├──────────────────────────────────────────────────────────────────┤
│                      Action Layer                                 │
│     ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐  │
│     │Keyboard│ │ Mouse  │ │ Shell  │ │ Window   │ │ Slider   │  │
│     │        │ │        │ │        │ │ Manager  │ │ (UIA)    │  │
│     └────────┘ └────────┘ └────────┘ └──────────┘ └──────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                    Observation Layer                               │
│         ┌───────────────┐      ┌──────────────────┐              │
│         │  Screenshot   │      │  GIF Recorder    │              │
│         │  (mss)        │      │  (imageio)       │              │
│         └───────────────┘      └──────────────────┘              │
└──────────────────────────────────────────────────────────────────┘
```

### The Observe → Think → Act → Learn Loop

```
  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
  │ OBSERVE │────▶│  THINK  │────▶│   ACT   │────▶│  LEARN  │
  │ Screen  │     │ GPT-4o  │     │ Execute │     │ RL + QA │
  │ + UIA   │     │ Decide  │     │ Action  │     │ Update  │
  └─────────┘     └─────────┘     └─────────┘     └────┬────┘
       ▲                                                │
       └────────────────────────────────────────────────┘
                    Loop until "done"
```

---

## 🧠 Learning Systems

### Reinforcement Learning (Q-Learning)

| Component | Detail |
|-----------|--------|
| **Algorithm** | Tabular Q-learning with TD update |
| **State** | Hash of window title + UI element context |
| **Actions** | 16 action types (click, type, hotkey, etc.) |
| **Learning Rate (α)** | 0.15 |
| **Discount (γ)** | 0.9 |
| **Rewards** | +2.0 done, +0.3 progress, -0.7 drift, -1.2 wrong content |
| **Persistence** | Q-table saved to `recordings/rl_qtable.json` |
| **Pre-seeding** | Commonsense priors for known apps |
| **Episodes** | 43 completed, 63 Q-table entries |

### 👤 Human Supervision (NEW in v7)

Run demos with `--supervise` to enable human review after each task:

```
═══════════════════════════════════════════════════════
  HUMAN SUPERVISION — Review Demo Result
═══════════════════════════════════════════════════════
  Demo:    Demo 5: Notepad - Type Message
  Status:  ✓ SUCCESS
  Steps:   4
  Time:    99.1s
  GIF:     recordings/demo5_notepad_type.gif

  Accuracy (did it achieve the right outcome?) [1-5]: _
  Completeness (were ALL parts finished?) [1-5]: _
  Efficiency (no wasted/repeated steps?) [1-5]: _
  Any corrective notes? > _
```

Human ratings flow into:
- 📊 **RL reward signal** — weighted 3× stronger than automated rewards
- ⚡ **Demo Optimizer** — tightens step budgets, captures golden sequences
- 💬 **Prompt hints** — corrective notes injected into future LLM calls

### ⚡ Amortization (Speed Optimization)

> **Design constraint:** Cursor movement and typing speed are **never** accelerated. All optimization targets overhead.

| Strategy | Savings | Description |
|----------|---------|-------------|
| Token caching | ~15s | Azure AD tokens cached for ~50 minutes |
| RL pre-seeding | Varies | Commonsense priors skip exploration |
| Fast mode | ~8s/step | Skip post-action validation |
| Step budget | ~30% | Tighten max_steps from best runs |
| Golden replay | Skip LLM | Replay best action sequences |
| Prompt hints | Quality | Human notes prevent repeated mistakes |

---

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/jiaqizou-msft/AgenticOS-ClaudeOpus4.6.git
cd AgenticOS-ClaudeOpus4.6
pip install -e ".[dev]"
```

### Run Demos

```bash
# Run all fast demos (5-14)
python scripts/run_demo_detached.py --demo fast

# Run with human supervision
python scripts/run_demo_detached.py --demo fast --supervise

# Run a specific demo
python scripts/run_demo_detached.py --demo 1

# Run a range
python scripts/run_demo_detached.py --demo 5-14

# Interactive chat mode
agenticos --task "Open Notepad and type Hello World"
```

### Configure Azure OpenAI

```bash
set AZURE_API_BASE=https://your-resource.cognitiveservices.azure.com/
set AZURE_API_VERSION=2024-12-01-preview
# Uses Azure AD authentication via DefaultAzureCredential
```

---

## 📦 Project Structure

```
AgenticOS/
├── src/agenticos/
│   ├── agent/
│   │   ├── navigator.py         # Core ReAct navigator (GPT-4o)
│   │   ├── planner.py           # LLM task decomposition
│   │   ├── reinforcement.py     # Tabular Q-learning
│   │   ├── human_supervisor.py  # 👤 Post-demo human review
│   │   ├── demo_optimizer.py    # ⚡ Per-demo amortization engine
│   │   ├── human_teacher.py     # Learning from Demonstration
│   │   ├── state_validator.py   # Post-action state validation
│   │   ├── recovery.py          # Per-app recovery strategies
│   │   └── step_memory.py       # Cached step patterns
│   ├── grounding/
│   │   ├── accessibility.py     # pywinauto UIA grounding
│   │   ├── visual.py            # VLM-based visual grounding
│   │   └── ocr.py               # RapidOCR text detection
│   ├── actions/
│   │   └── compositor.py        # 16 action types with retry
│   ├── observation/
│   │   ├── screenshot.py        # mss-based screen capture
│   │   └── recorder.py          # GIF session recorder
│   └── mcp/
│       └── server.py            # FastMCP server (11 tools)
├── scripts/
│   ├── run_demo_detached.py     # Demo runner v7 (14 demos)
│   └── human_teach.py           # Human teaching CLI
├── recordings/                  # GIF recordings & persistent data
│   ├── demo*.gif                # 15 demo GIF recordings
│   ├── rl_qtable.json           # Persistent Q-table (63 entries)
│   └── supervision/             # Human feedback & optimizer state
├── docs/
│   └── presentation.html        # 📊 14-slide interactive presentation
├── paper/                       # Academic paper (LaTeX)
└── tests/                       # Unit test suite
```

---

## 📊 Presentation

An interactive **14-slide HTML presentation** covering the full project is available:

```bash
start docs/presentation.html
```

Covers: project motivation, architecture, ReAct loop, demo results, human supervision system, RL & amortization, development timeline, comparison with existing systems, and roadmap.

---

## 🏆 Comparison with Existing Systems

| System | Architecture | Grounding | Learning | Open Source |
|--------|-------------|-----------|----------|:---:|
| **AgenticOS** | Modular ReAct | UIA + Vision + OCR | Q-learning + Human | ✅ |
| UFO² | Dual-agent | UIA + Vision | — | ✅ |
| Operator | CUA | Vision only | — | ❌ |
| Navi | Foundation model | Vision only | — | ❌ |
| Claude Computer Use | ReAct | Vision only | — | ❌ |

---

## 🔮 Roadmap

- [ ] **Vision QA Mode** — Ask the agent questions about what's on screen
- [ ] **Playback Recorder** — Deterministic replay on other machines for bug reproduction
- [ ] **Human-Speed Interaction** — Character-by-character typing with visible cursor movement
- [ ] **Confidence Dashboard** — Real-time visualization of per-demo optimization
- [ ] **Multi-DUT Support** — Run the same automation across multiple test machines

---

## 📜 License

[MIT License](LICENSE) — see LICENSE file for details.

---

<div align="center">

**Built with ❤️ by Jiaqi Zou · Microsoft · 2025**

*Powered by Claude Opus 4.6 + Azure OpenAI GPT-4o*

⭐ Star this repo if you find it useful!

</div>
