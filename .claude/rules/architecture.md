# AgenticOS — Architecture Rules

## Module Boundaries
- `observation/` ONLY captures screen state — never executes actions
- `grounding/` ONLY identifies UI elements — never executes actions
- `actions/` ONLY executes OS actions — never captures or reasons
- `agent/` orchestrates observation → reasoning → action
- `mcp/` exposes capabilities as MCP tools — delegates to other modules
- `evaluation/` measures performance — never modifies system state

## Data Flow
```
User Input → CLI → Agent.navigate(task)
  → Observation.capture() → screenshot + metadata
  → Grounding.detect(screenshot) → list[UIElement]
  → LLM.think(screenshot, elements, history) → Action
  → Actions.execute(action) → result
  → loop until done or max_steps
```

## Key Interfaces
- `Agent.observe() -> Observation` — capture current screen state
- `Agent.think(observation) -> Action` — LLM reasoning
- `Agent.act(action) -> ActionResult` — execute and verify
- `Grounder.detect(screenshot) -> list[UIElement]` — find interactive elements
- `ActionExecutor.execute(action) -> ActionResult` — perform OS action

## Configuration
- Use `pydantic-settings` with env vars (AGENTICOS_* prefix)
- Config file: `agenticos.toml` or env vars
- Sensitive values (API keys) ONLY via env vars, never in config files
