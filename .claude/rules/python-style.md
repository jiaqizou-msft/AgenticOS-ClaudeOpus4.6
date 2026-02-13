# AgenticOS — Python Style Rules

## Formatting
- Line length: 100 characters (enforced by ruff)
- Indentation: 4 spaces (standard Python)
- Imports: sorted by ruff (isort-compatible), grouped: stdlib → third-party → local

## Type Annotations
- All public functions MUST have type annotations
- Use `from __future__ import annotations` for forward references
- Use `typing.Protocol` for interfaces, not ABCs where possible
- Use `pydantic.BaseModel` for data classes with validation

## Naming
- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: prefix with `_`

## Docstrings
- Google style docstrings on all public classes and functions
- Include Args, Returns, Raises sections

## Error Handling
- Use specific exception types, never bare `except:`
- Create custom exceptions in `utils/exceptions.py`
- Log errors with `rich.console` or `logging`

## Async
- Use `async def` for I/O-bound operations (LLM calls, file I/O)
- Use `asyncio.gather` for parallel async operations
- Sync wrappers use `asyncio.run()` at entry points only
