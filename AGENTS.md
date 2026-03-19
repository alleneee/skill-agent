# AGENTS.md

This file provides guidance to AI agents when working within this repository.

## Build and Test

```bash
# Install dependencies
make install        # or: uv sync

# Run tests
make test           # uv run pytest -v
make test-cov       # with coverage

# Code quality
make check          # lint + format-check + type-check
make lint-fix       # auto-fix lint issues

# Single test
uv run pytest tests/core/test_agent.py -v

# Dev server
make dev            # uvicorn with hot reload on port 8000
```

Always use `uv run` instead of direct `python`.

## Architecture

```text
API Layer (FastAPI)          -> src/omni_agent/api/
Core Layer (Agent/Team/...)  -> src/omni_agent/core/
Tool Layer (Base/MCP/Skills) -> src/omni_agent/tools/
Service Layer (RAG/Sandbox)  -> src/omni_agent/rag/, sandbox/, acp/
```

Entry point: `src/omni_agent/main.py`
Config: `src/omni_agent/core/config.py` (pydantic-settings, loads from `.env`)
Dependency injection: `src/omni_agent/api/deps.py`

Import path: `from omni_agent.core import Agent` (never use `src.` prefix)

## Conventions

- File/function names: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- API endpoints: `kebab-case`
- All public functions must have type annotations
- Use `from __future__ import annotations` for deferred evaluation
- Comments in Chinese, explaining "why" not "what"
- Commit format: `<type>: <description in Chinese>`

## Done When

### New Feature

- Code passes `make check`
- Unit tests added in corresponding `tests/<layer>/` directory
- README updated if API surface changed
- Config documented in `config.py` with Field description

### Bug Fix

- Reproduction test added and passes
- All existing tests still pass
- Root cause identified (not just symptom patched)

### Refactor

- Behavior unchanged, all tests pass
- No new lint warnings
- No new dependencies unless justified

## Evaluation

```bash
# Internal evals (61 cases across 6 categories)
uv run python -m omni_agent.eval --tags quick

# External benchmarks
uv run python -m omni_agent.eval.benchmarks bfcl --categories simple --max-cases 20
uv run python -m omni_agent.eval.benchmarks gaia --levels 1 --max-cases 10
```

Eval cases: `evals/*/cases.yaml`
Benchmark adapters: `src/omni_agent/eval/benchmarks/`

## Tool Descriptions

| Tool | Correct Usage | Common Mistake |
|------|--------------|----------------|
| `read_file` | Read with offset/limit for large files | Reading entire huge files |
| `write_file` | Create new files or full rewrites | Use `edit_file` for partial changes |
| `edit_file` | Targeted string replacement | old_string not unique in file |
| `bash` | Shell commands with timeout | Running without timeout on long ops |
| `spawn_agent` | Bounded subtasks with clear role | Spawning for trivial single-step tasks |
| `search_knowledge` | RAG queries when ENABLE_RAG=true | Searching before knowledge is indexed |

## Harness (Engineering Guidelines)

Development specifications are in `harness/` directory. Read the relevant document before making changes:

| Document | Scope |
|----------|-------|
| `harness/ARCHITECTURE.md` | System layering, component relationships, data flow |
| `harness/RULES.md` | Code style, naming, imports, Git workflow |
| `harness/TESTING.md` | Test pyramid, fixtures, mock strategies, coverage |
| `harness/CI.md` | CI/CD pipeline stages |
| `harness/STRUCTURE.md` | Directory tree, module placement rules |
| `harness/VALIDATION.md` | Pre-commit, CI, deployment checklists |
| `harness/AGENT_BEHAVIOR.md` | Execution loop, tool constraints, multi-agent rules |
| `harness/TOOL_DEVELOPMENT.md` | Tool interface contract, parameter schema, error handling |
| `harness/PROMPT_ENGINEERING.md` | System prompt design, tool descriptions, context management |
| `harness/MULTI_AGENT_PATTERNS.md` | Team/MsgHub/Ralph/SpawnAgent selection and anti-patterns |
| `harness/OBSERVABILITY.md` | AgentLogger, TraceLogger, event system, debugging |
| `harness/EVALUATION.md` | Eval case design, grading, metrics |
| `harness/SECURITY.md` | Sandbox, prompt injection defense, access control |

## Common Mistakes

1. Importing as `from src.omni_agent...` instead of `from omni_agent...`
2. Loading MCP tools per-request instead of at startup in lifespan
3. Using `LLM_MODEL` without `provider/model` format
4. Forgetting `uv run` prefix when executing scripts
5. Creating files outside `workspace_dir` boundary
6. Not checking `cancel_event` in long-running tool execution
7. Exceeding `SPAWN_AGENT_MAX_DEPTH` with recursive agent spawning
