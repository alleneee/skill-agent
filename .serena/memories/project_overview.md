# Omni Agent - Project Overview

## Purpose
AI Agent framework with tool execution capabilities, multi-agent collaboration (Team, MsgHub, Ralph), MCP integration, RAG knowledge base, and ACP protocol support.

## Tech Stack
- Python 3.11+, FastAPI, Pydantic v2, LiteLLM
- uv package manager, ruff linter/formatter
- PostgreSQL + pgvector for RAG
- Redis optional for session storage

## Key Directories
- `src/omni_agent/core/` - Agent, Team, Session, Config
- `src/omni_agent/tools/` - Tool implementations
- `src/omni_agent/api/` - FastAPI endpoints
- `src/omni_agent/acp/` - Agent Client Protocol
- `src/omni_agent/rag/` - RAG knowledge base
- `tests/` - Test suite

## Commands
- `make install` / `uv sync` - Install deps
- `make dev` - Dev server
- `make test` - Run tests
- `make lint` / `make format` - Code quality
- `make check` - All checks

## Code Style
- Chinese comments
- Type hints throughout
- Pydantic models for config/schemas
- Async/await patterns
- `from omni_agent.xxx import` (not `from src.`)
