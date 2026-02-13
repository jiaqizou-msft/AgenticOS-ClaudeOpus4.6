# AgenticOS — Testing Rules

## Test Structure
- Unit tests in `tests/unit/` — mirror `src/agenticos/` structure
- Integration tests in `tests/integration/` — real OS interaction tests
- Benchmark tests in `tests/benchmarks/` — pytest-benchmark performance tests

## Conventions
- Test files: `test_<module>.py`
- Test functions: `test_<what>_<condition>_<expected>()`
- Use `pytest.fixture` for shared setup
- Use `pytest.mark.parametrize` for data-driven tests
- Use `pytest.mark.integration` for tests that interact with the real OS
- Use `pytest.mark.benchmark` for performance benchmarks
- Use `pytest.mark.slow` for tests taking >10 seconds

## Assertions
- Use plain `assert` with descriptive messages
- For complex assertions, use helper functions

## Mocking
- Mock LLM API calls in unit tests (never call real APIs)
- Mock `pyautogui` / `pywinauto` in unit tests
- Integration tests may use real OS but must clean up after themselves

## Benchmarks
- Use `benchmark` fixture from pytest-benchmark
- Always set `min_rounds=3` for stability
- Export results as JSON for CI regression tracking
