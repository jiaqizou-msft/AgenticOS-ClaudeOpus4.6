<div align="center">

# 🖥️ AgenticOS — Project Presentation

### Turn Windows into an AI-Navigable Desktop

**Built by Jiaqi Zou · Microsoft · 2025-2026**
*Powered by Claude Opus 4.6 + Azure OpenAI GPT-4o*

---

</div>

## 📑 Table of Contents

1. [The Problem](#slide-1--the-problem)
2. [Architecture](#slide-2--architecture)
3. [The Observe → Think → Act Loop](#slide-3--the-observe--think--act-loop)
4. [v1: 14 Live Demos](#slide-4--v1-14-live-demos)
5. [v2: 50 New Multi-App Demos](#slide-5--v2-50-new-multi-app-demos)
6. [By The Numbers](#slide-6--by-the-numbers)
7. [Human Supervision System](#slide-7--human-supervision-system)
8. [RL & Amortization](#slide-8--rl--amortization)
9. [Key Innovations](#slide-9--key-innovations)
10. [Comparison](#slide-10--comparison)
11. [Roadmap](#slide-11--roadmap)

---

## Slide 1 — The Problem

### Why do we need AI desktop agents?

| Challenge | Description |
|:---:|:---|
| 🔄 **Repetitive GUI Tasks** | Users spend hours on repetitive desktop workflows that could be automated — but traditional scripting is fragile and breaks with UI changes. |
| 🧪 **QA & Bug Reproduction** | Testers need to reproduce bugs across different machines. An AI agent can record and replay complex multi-app scenarios on any DUT. |
| ♿ **Accessibility Automation** | Accessibility testing requires navigating every UI element. An agent that reads the UIA tree can systematically verify compliance at scale. |
| 🌐 **Cross-App Orchestration** | Real workflows span Outlook → Teams → Browser → Explorer. Existing tools automate single apps. AgenticOS coordinates across the full desktop. |
| 📈 **Learning from Humans** | The agent improves over time through RL rewards and human supervision feedback — becoming faster and more accurate with each run. |

---

## Slide 2 — Architecture

### Five-layer modular design

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

---

## Slide 3 — The Observe → Think → Act Loop

### How the agent processes each step

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

| Phase | Details |
|-------|---------|
| 📸 **Observe** | Capture screenshot (mss) + UIA accessibility tree (pywinauto). Extract element names, bounding boxes, values. |
| 🧠 **Think** | Send screenshot + element tree to GPT-4o. Receives JSON: `{thought, action}`. RL checks confidence. Optimizer injects hints. |
| ⚡ **Act** | Execute action via compositor (17 action types). Post-action validation detects drift. Recovery manager corrects mistakes. |
| 📊 **Learn** | Update Q-table with reward signal. Store successful patterns in step memory. Human supervisor rates the result. |

---

## Slide 4 — v1: 14 Live Demos

### Real Windows 11 automation, recorded as GIFs

| # | Demo | Application | Steps | Time | Status | Human Rating |
|---|------|-------------|-------|------|--------|:---:|
| 1 | System Tray — Brightness & Volume | Quick Settings | 5 | 68s | ✅ PASS | — |
| 2 | Edge — 4K YouTube Fullscreen | Edge + YouTube | 9 | 138s | ✅ PASS | — |
| 3 | Outlook Email + Teams Message | Outlook + Teams | — | — | 🔄 WIP | — |
| 4 | File Explorer — Create Folder | Explorer | 15 | 220s | ✅ PASS | — |
| 5 | Notepad — Type Message | Notepad | 4 | 99s | ✅ PASS | ⭐ 1/5 |
| 6 | Calculator — 123 + 456 | Calculator | 3 | 53s | ⚠️ Issues | 0/5 |
| 7 | CMD — Echo Command | CMD | 3 | 56s | ⚠️ Issues | 0/5 |
| 8 | Settings — About Page | Settings | 2 | 28s | ✅ PASS | ⭐ 1/5 |
| 9 | Notepad — Select All & Copy | Notepad | 5 | 74s | ✅ PASS | ⭐ 1/5 |
| 10 | Notepad — Find Text | Notepad | 3 | 49s | ✅ PASS | ⭐ 1/5 |
| 11 | Calculator — 7 × 8 | Calculator | 4 | 65s | ✅ PASS | ⭐ 1/5 |
| 12 | PowerShell — Get-Date | PowerShell | 3 | 43s | ✅ PASS | ✅ |
| 13 | Notepad — Undo Typing | Notepad | 6 | 105s | ❌ FAIL | 0/5 |
| 14 | Task Manager — View Processes | Task Manager | 2 | 36s | ✅ PASS | ⭐ 1/5 |

> **v1 Summary:** 10/14 autonomous pass · 2 partial · 1 failure · 1 WIP

---

## Slide 5 — v2: 50 New Multi-App Demos

### Expanding from 8 apps to 15+

| App Category | App | Demo Range | Count | Difficulty |
|:---:|:---|:---:|:---:|:---|
| 🌐 | **Microsoft Edge** | 15-22 | 8 | Beginner → Advanced |
| 💬 | **Microsoft Teams** | 23-30 | 8 | Beginner → Advanced |
| 📧 | **Microsoft Outlook** | 31-38 | 8 | Beginner → Advanced |
| 📱 | **Surface App** | 39-42 | 4 | Beginner → Intermediate |
| ⚙️ | **Windows Settings** | 43-50 | 8 | Beginner → Advanced |
| 📁 | **File Explorer** | 51-54 | 4 | Beginner |
| ✂️🎨 | **Snipping Tool / Paint** | 55-56 | 2 | Beginner |
| 🏪 | **Microsoft Store** | 57-58 | 2 | Beginner |
| 📝📊📽️ | **Word / Excel / PowerPoint** | 59-61 | 3 | Beginner |
| 🔒📋💬 | **Security / Clipboard / Feedback** | 62-64 | 3 | Beginner-Intermediate |

### v2 Before & After Comparison

| Metric | Before (v1) | After (v2) | Change |
|--------|:-----------:|:----------:|:------:|
| **Total Demos** | 14 | **64** | +357% |
| **Apps Covered** | 8 | **15+** | +88% |
| **RL Pre-seed Priors** | 6 | **19** | +217% |
| **Recovery Strategies** | 13 | **21** | +62% |
| **Teaching Topics** | 11 | **17** | +55% |
| **Q-Table Entries** | 63 | **116** | +84% |
| **RL Episodes** | 43 | **65** | +51% |
| **New Features** | — | `--app`, `--difficulty`, `--iterations` | 🆕 |

### v2 Early Results

| App | Tested | Pass | Partial | Status |
|-----|:------:|:----:|:-------:|--------|
| Settings | 3 | 2 | 1 | ✅ 67% pass rate |
| Edge | 1 | 0 | 1 | ⚠️ Address bar navigation |
| Others | 0 | 0 | 0 | 🔄 Pending |

---

## Slide 6 — By The Numbers

<div align="center">

| Metric | Value |
|:------:|:-----:|
| 🎬 **Total Demos** | **64** |
| ✅ **v1 Success Rate** | **71%** |
| ⚡ **Action Types** | **17** |
| 🧠 **Q-Table Entries** | **116** |
| 📈 **RL Episodes** | **65** |
| 👤 **Human Reviews** | **10** |
| 🔧 **MCP Tools** | **11** |
| 📱 **Apps Supported** | **15+** |
| 🏗️ **Architecture Layers** | **5** |
| 🔄 **Recovery Strategies** | **21** |

</div>

---

## Slide 7 — Human Supervision System

### The agent learns from your feedback

**Review Phase** — After each demo:
- GIF recording of the full run
- Step-by-step action log
- Success/failure status & timing

**Rating Phase** — Human rates three dimensions (1-5):
- **Accuracy** — Right outcome? (2× weight)
- **Completeness** — All parts done?
- **Efficiency** — No wasted steps?

**How feedback flows:**
- 📊 **RL reward signal** — weighted 3× stronger than automated rewards
- ⚡ **Demo Optimizer** — tightens step budgets, captures golden sequences
- 💬 **Prompt hints** — corrective notes injected into future LLM calls

```
python scripts/run_demo_detached.py --demo fast --supervise

  ════════════════════════════════════════════════════════════════
    HUMAN SUPERVISION — Review Demo Result
  ════════════════════════════════════════════════════════════════
    Demo:    Demo 44: Settings - Display
    Status:  ✓ SUCCESS
    Steps:   2
    Time:    55.4s
    GIF:     recordings/v2/demo44_settings_display.gif

    Accuracy (did it achieve the right outcome?) [1-5]: _
    Completeness (were ALL parts finished?) [1-5]: _
    Efficiency (no wasted/repeated steps?) [1-5]: _
    Any corrective notes? > _
```

---

## Slide 8 — RL & Amortization

### Getting faster without getting sloppy

**Tabular Q-Learning:**
- State = hash(window_title + UI elements)
- Action = one of 17 action types
- Update: Q(s,a) ← Q(s,a) + α[r + γ·max Q(s',a') − Q(s,a)]
- α = 0.15, γ = 0.9

**Reward Signal:**

| Reward | Source |
|:------:|--------|
| +2.0 | Task done successfully |
| +0.3 | State changed (progress) |
| +1.5 | Speed bonus (fast completion) |
| −0.7 | State drift detected |
| −1.2 | Wrong content selected |
| +3.0 | Human rates 5/5 |
| −2.0 | Human rates 1/5 |

**Amortization Strategies:**

| Strategy | Savings | Description |
|----------|---------|-------------|
| Token caching | ~15s | Azure AD tokens cached ~50min |
| RL pre-seeding | Varies | Commonsense priors for 19 apps |
| Fast mode | ~8s/step | Skip post-action validation |
| Step budget | ~30% | Tighten max_steps from good runs |
| Golden replay | Skip LLM | Replay best action sequences |
| Prompt hints | Quality | Human notes prevent mistakes |
| Iteration mode | 5× | `--iterations 5` for refinement |

---

## Slide 9 — Key Innovations

| Innovation | Details |
|:---:|:---|
| 🎚️ **UIA Slider Control** | Direct `RangeValuePattern.SetValue()` via Windows UI Automation. 100% reliable vs unreliable mouse drag. |
| 🔍 **Content Verification** | Post-click window title checking prevents wrong content selection. Essential for browser automation. |
| 🔄 **Recovery-Aware Actions** | Per-app recovery strategies that know when NOT to intervene (e.g., during rename dialogs). 21 app-specific strategies. |
| ✅ **Filesystem Verification** | Before accepting "done", verify outcomes on disk (e.g., check folder actually exists). |
| 👤 **Human > Automated Metrics** | Demos passing automated checks may still fail human quality expectations. Human RL signal catches nuances. |
| ⚡ **Speed ≠ Mouse Speed** | Optimization targets overhead (LLM latency, UIA detection) not physical interaction speed. |
| 🏷️ **App/Difficulty Filtering** | `--app edge --difficulty beginner` narrows demo scope for focused testing. |
| 🔁 **Iteration Mode** | `--iterations 5` reruns demos to accumulate RL signal and improve via learning. |

---

## Slide 10 — Comparison

| System | Architecture | Grounding | Learning | Apps | Human-in-Loop | Open Source |
|--------|:-----------:|:---------:|:--------:|:----:|:---:|:---:|
| **AgenticOS v2** | Modular ReAct | UIA + Vision + OCR | Q-Learning + Human | **15+** | ✅ | ✅ |
| UFO² | Dual-agent | UIA + Vision | None | — | ❌ | ✅ |
| Operator | CUA | Vision only | None | — | ❌ | ❌ |
| Navi | Foundation | Vision only | None | — | ❌ | ❌ |
| Claude Computer Use | ReAct | Vision only | None | — | ❌ | ❌ |

**AgenticOS differentiators:**
- Triple-layer grounding (UIA + Vision + OCR)
- Online RL with persistent Q-table (116 entries, 65 episodes)
- Human supervision with feedback-driven optimization
- Golden sequence replay for amortization
- 15+ real Windows applications with app-specific recovery

---

## Slide 11 — Roadmap

- [x] **v1: Core Demos** — 14 demos across 8 apps
- [x] **Human Supervision** — Review, rate, and correct demos
- [x] **Demo Optimizer** — Per-demo amortization with golden sequences
- [x] **v2: Multi-App Expansion** — 50 new demos across 15 apps
- [x] **App Filtering** — `--app edge`, `--difficulty beginner`
- [x] **Iteration Mode** — `--iterations 5` for iterative refinement
- [ ] **Vision QA Mode** — Ask the agent questions about what's on screen
- [ ] **Playback Recorder** — Deterministic replay for bug reproduction
- [ ] **Multi-DUT Support** — Run automation across multiple machines
- [ ] **Confidence Dashboard** — Real-time visualization of optimization

---

<div align="center">

## 🖥️✨ Thank You

**AgenticOS — Making Windows AI-navigable**

[GitHub: jiaqizou-msft/AgenticOS-ClaudeOpus4.6](https://github.com/jiaqizou-msft/AgenticOS-ClaudeOpus4.6)

```
python scripts/run_demo_detached.py --demo v2 --app settings --supervise
```

*Built with Claude Opus 4.6 · Azure OpenAI GPT-4o · Python · Windows UI Automation*

</div>
