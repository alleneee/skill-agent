# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses **uv** as the package manager (faster than pip) and **Make** for common tasks.

### Essential Commands
```bash
# Install dependencies
make install        # or: uv sync

# Development server (with hot reload)
make dev            # or: uv run uvicorn omni_agent.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
make test           # or: uv run pytest -v
make test-cov       # Run tests with coverage

# Code quality
make lint           # Check code with ruff
make lint-fix       # Auto-fix linting issues
make format         # Format code with ruff
make check          # Run all checks (lint, format, type)

# Single test file
uv run pytest tests/core/test_agent.py -v

# Specific test function
uv run pytest tests/core/test_agent.py::test_function_name -v
```

### Important Notes
- **Always use `uv run`** instead of direct `python` when running scripts
- The project uses **Python 3.11+** (required)
- Source code is in `src/omni_agent/`, not root level

## Architecture Overview

### Core Components

**1. Agent Execution Loop** (`src/omni_agent/core/agent.py`)
- Manages the complete AI agent lifecycle
- Integrates TokenManager for context management (prevents overflow at 120k tokens)
- Integrates AgentLogger for structured JSON logging
- Executes multi-step tasks with tool calls until completion or max_steps reached

**2. Token Management** (`src/omni_agent/core/token_manager.py`)
- Uses tiktoken (cl100k_base) for precise token counting
- Automatically summarizes message history when exceeding token_limit
- Summarization strategy: keeps all user messages, compresses agent execution rounds
- Can reduce token usage by 50-70% while preserving context

**3. Structured Logging** (`src/omni_agent/core/agent_logger.py`)
- Creates timestamped log files: `~/.omni-agent/log/agent_run_YYYYMMDD_HHMMSS.log`
- Logs: STEP (token usage), REQUEST, RESPONSE, TOOL_EXECUTION (with timing), COMPLETION
- Critical for debugging agent behavior and performance analysis

**4. MCP Integration** (`src/omni_agent/services/mcp_manager.py`, `src/omni_agent/tools/mcp_loader.py`)
- Loads external tools via Model Context Protocol at startup
- Configuration in `mcp.json` (supports stdio, SSE, HTTP transports)
- Tools stored globally in `api/deps.py` and injected into agent
- **Important**: MCP tools must be loaded during FastAPI lifespan startup, not per-request

### Request Flow

```
HTTP Request → FastAPI Router (api/v1/agent.py)
            ↓
    Dependency Injection (api/deps.py)
    - get_llm_client()
    - get_tools() [includes MCP + base + skills]
            ↓
    Agent.run() (core/agent.py)
    - TokenManager checks/summarizes
    - AgentLogger records each step
    - LLM generates response
    - Tools execute (with timing)
    - Loop until complete or max_steps
            ↓
    Return response with execution_logs
```

### Tool System

**Tool Loading Priority** (in `api/deps.py:get_tools()`):
1. Base tools: ReadTool, WriteTool, EditTool, BashTool
2. MCP tools: Loaded at startup via `initialize_mcp_tools()`
3. Skills: Dynamically loaded via SkillTool

**Adding New Tools**:
1. Create tool class inheriting from `Tool` base class (`tools/base.py`)
2. Implement: `name`, `description`, `parameters`, `execute()` method
3. Register in `api/deps.py:get_tools()` function
4. Tools are automatically exposed in OpenAPI schema

### Configuration System

Uses **pydantic-settings** with `.env` file support (`core/config.py`):

**Critical Settings**:
- `ENABLE_MCP=true`: Must be true for MCP tools to load
- `ENABLE_SKILLS=true`: Must be true for Skills system
- `ENABLE_RAG=true`: Must be true for RAG knowledge base
- `ENABLE_SPAWN_AGENT=true`: Must be true for spawn_agent tool
- `MCP_CONFIG_PATH=mcp.json`: Path to MCP configuration
- `LLM_API_KEY`: Required for LLM calls
- `LLM_MODEL`: Model name in `provider/model` format (e.g., `anthropic/claude-3-5-sonnet-20241022`)
- `AGENT_MAX_STEPS=50`: Prevents infinite loops
- Token management is always enabled (120k default limit)

**SpawnAgent Settings**:
- `SPAWN_AGENT_MAX_DEPTH=3`: Maximum nesting depth for spawned agents
- `SPAWN_AGENT_DEFAULT_MAX_STEPS=15`: Default max steps for child agents
- `SPAWN_AGENT_TOKEN_LIMIT=50000`: Token limit for child agents

**ACP Settings** (Agent Client Protocol):
- `ENABLE_ACP=true`: Enable ACP protocol endpoints for code editor integration

**Sandbox Settings** (when `ENABLE_SANDBOX=true`):
- `SANDBOX_URL=http://localhost:8080`: agent-sandbox server URL
- `SANDBOX_AUTO_START=false`: Auto-start Docker container if not running
- `SANDBOX_DOCKER_IMAGE=ghcr.io/agent-infra/sandbox:latest`: Docker image
- `SANDBOX_TTL_SECONDS=3600`: Sandbox instance TTL (1 hour default)
- `SANDBOX_MAX_INSTANCES=100`: Maximum concurrent sandbox instances

**Session Settings**:
- `SESSION_BACKEND=file`: Storage backend (file, redis, postgres)
- `SESSION_MAX_AGE_DAYS=7`: Session expiration
- `SESSION_HISTORY_RUNS=3`: Number of previous runs to include in context

**RAG Settings**:
- `DASHSCOPE_API_KEY`: Required for embedding generation
- `EMBEDDING_MODEL=text-embedding-v4`: Embedding model
- `CHUNK_SIZE=500`: Document chunk size
- `RAG_TOP_K=5`: Number of search results

**Environment Variables vs Config**:
- `.env` is primary configuration source
- Settings are validated and processed in `Settings` class
- Access via global `settings` instance

### Skills System

**Location**: `src/omni_agent/skills/` (internal) and `./skills/` (external)

**Architecture**:
- Each skill is a directory with `SKILL.md` file
- `SkillTool` (`skills/skill_tool.py`) loads skills on-demand via `get_skill` tool
- Skills provide expert guidance (not executable code)
- System prompt automatically includes skill metadata when `ENABLE_SKILLS=true`

**Skill Structure**:
```
skills/my-skill/
├── SKILL.md          # Main skill content (loaded by get_skill tool)
└── reference/        # Optional supporting docs
```

### MCP Configuration

**File**: `mcp.json` (JSON schema: https://modelcontextprotocol.io/schema/mcp.json)

**Structure**:
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",              // or python, node, etc.
      "args": ["-y", "package-name"],
      "env": {"API_KEY": "value"},   // Environment variables for server
      "disabled": false              // Set true to disable without removing
    }
  }
}
```

**Common Issue**: If MCP tools don't load:
1. Check `ENABLE_MCP=true` in `.env`
2. Verify `mcp.json` exists and is valid JSON
3. Check startup logs for MCP initialization messages
4. Debug logs written to `/tmp/mcp_init_debug.log`

### ACP Integration (Agent Client Protocol)

**Location**: `src/omni_agent/acp/`

Implements [Zed Agent Client Protocol](https://agentclientprotocol.com/) for code editor integration.

**Architecture**:
- `schemas.py`: JSON-RPC 2.0, Session, ToolCall, ContentBlock data models
- `adapter.py`: Converts between ACP and internal message formats
- `api/v1/endpoints/acp.py`: HTTP endpoints for ACP protocol

**Endpoints** (when `ENABLE_ACP=true`):
- `POST /api/v1/acp/agent/initialize`: Initialize connection, negotiate capabilities
- `POST /api/v1/acp/session/new`: Create new session
- `POST /api/v1/acp/session/prompt`: Process user prompt (sync)
- `POST /api/v1/acp/session/prompt/stream`: Process user prompt (streaming SSE)
- `POST /api/v1/acp/session/cancel`: Cancel session operation

**Session Updates** (streaming events):
- `agent_thought_chunk`: LLM thinking process
- `agent_message_chunk`: Agent response content
- `tool_call`: Tool invocation start
- `tool_call_update`: Tool execution status/result
- `plan`: Execution plan (TODO list)

### Multi-LLM Provider Support

System supports **100+ LLM providers** via LiteLLM with automatic parameter adaptation:

**Supported Providers**:
- Anthropic: `anthropic/claude-3-5-sonnet-20241022` (max_tokens: 8192)
- OpenAI: `openai/gpt-4o` (max_tokens: 16384)
- xAI: `xai/grok-4-fast-reasoning` (max_tokens: 16384)
- DeepSeek: `deepseek/deepseek-chat` (max_tokens: 8192)
- Qwen: `qwen/qwen-max` (max_tokens: 8192)

**Auto-Standardization**: Model names are automatically converted to `provider/model` format
```bash
claude-3-5-sonnet-20241022  → anthropic/claude-3-5-sonnet-20241022
gpt-4o                      → openai/gpt-4o
```

**Auto-Adjustment**: `max_tokens` is automatically capped to provider limits
```
Request 16384 → DeepSeek limit 8192 → Auto-adjusted to 8192
```

See `docs/MODEL_STANDARDIZATION.md` for detailed configuration.

### SpawnAgent Tool

`spawn_agent` allows parent agent to dynamically create child agents for delegated tasks:

**Parameters**:
- `task`: Task description for the child agent
- `role`: Role description (e.g., "security auditor", "test writer")
- `context`: Additional context for the child (optional)
- `tools`: List of tool names the child can use (optional)
- `max_steps`: Maximum steps for child execution (optional)

**Use Cases**:
- Tasks requiring specialized roles
- Breaking down complex tasks into independent subtasks
- Avoiding main agent context pollution

**Configuration**:
- `SPAWN_AGENT_MAX_DEPTH=3`: Prevents infinite nesting
- Child agents inherit token management and logging
- Execution tracked in TraceLogger for debugging

### Team Multi-Agent System

Team uses Leader-Member pattern for collaborative task execution (`src/omni_agent/core/team.py`):

**Architecture**:
1. Leader analyzes the task
2. Leader uses `delegate_task_to_member` tool to delegate to members
3. Members execute tasks and return results
4. Leader synthesizes final answer

**Predefined Roles** (in `core/team.py`):
- `researcher`: Information search and organization
- `writer`: Content writing and organization
- `coder`: Programming and technical tasks
- `reviewer`: Quality review and feedback
- `analyst`: Data analysis and insights

**Workflow Tracking**: All team runs are logged in TraceLogger with delegation chains

### MsgHub Event-Driven Multi-Agent Communication

MsgHub provides event-driven message broadcasting between agents (`src/omni_agent/core/msghub.py`):

**Core Mechanism**:
1. Each agent registers a COMPLETION event handler via EventEmitter
2. When an agent finishes speaking, the handler auto-broadcasts to all other participants
3. Other agents receive messages via `observe()` injection into their message history

**Components**:
- `MsgHub`: Orchestrates multi-agent discussions with event-driven broadcasting
- `MsgHubConfig`: Configuration (max_rounds, max_steps_per_turn, announcement)
- `Orchestrator`: Callable that selects the next speaker (defaults to round-robin)

**Agent Methods**:
- `Agent.observe(msg)`: Inject external message into agent's conversation history
- `Agent.execute_turn(max_steps)`: Execute one discussion turn, preserving external event handlers

**Usage**:
```python
from omni_agent.core import Agent, MsgHub, MsgHubConfig

designer = Agent(llm_client=llm, name="designer", system_prompt="UI designer")
developer = Agent(llm_client=llm, name="developer", system_prompt="Developer")

config = MsgHubConfig(max_rounds=6, max_steps_per_turn=5, announcement="Design review")

async with MsgHub([designer, developer], config=config) as hub:
    result = await hub.run("Design a REST API for user auth")
    hub.add(new_agent)       # Dynamic participant management
    hub.delete("designer")
```

**Completion**: Agent responds with `<hub_complete>` tag to signal discussion end.

### Ralph Iterative Mode

Ralph Loop is an iterative development methodology (`src/omni_agent/core/ralph.py`):

**Core Concept**: Same prompt executed repeatedly, AI sees previous work in files and iteratively improves until completion.

**Components**:
- `RalphConfig`: Configuration for iterations, completion conditions, context strategy
- `ToolResultCache`: Caches tool results with summaries, supports on-demand full retrieval
- `WorkingMemory`: Structured memory persisted to `.ralph/memory.json`
- `ContextManager`: Coordinates summarization and iteration history
- `CompletionDetector`: Multi-condition completion detection

**Usage**:
```python
from omni_agent.core import Agent, RalphConfig

# Simple: ralph=True uses default config
agent = Agent(llm_client=llm_client, tools=tools, ralph=True)

# Custom: ralph=RalphConfig(...) for custom settings
agent = Agent(
    llm_client=llm_client,
    tools=tools,
    ralph=RalphConfig(max_iterations=20, idle_threshold=3),
)

# Unified entry - run() auto-detects Ralph mode
result, logs = await agent.run(task="Refactor utils module")
```

**Completion Conditions**:
- `PROMISE_TAG`: Detects `<promise>TASK COMPLETE</promise>` tag
- `MAX_ITERATIONS`: Reached max iterations
- `IDLE_THRESHOLD`: No file changes for N consecutive iterations

**Ralph Tools** (auto-injected):
- `get_cached_result`: Retrieve full content of previous tool results
- `get_working_memory`: View memory summary
- `update_working_memory`: Update progress, findings, todos
- `signal_completion`: Signal task completion with promise tag

### Task Cancellation

Runtime cancellation mechanism for stopping long-running agent tasks (`src/omni_agent/core/run_manager.py`):

**Architecture**:
- `RunManager`: Global singleton managing active agent runs
- `asyncio.Event`: Used for cooperative cancellation signaling
- Cleanup: Incomplete messages are removed to maintain consistency

**Components**:
- `RunManager`: Registers/unregisters runs, handles cancellation
- `RunStatus`: Enum (RUNNING, COMPLETED, CANCELLED, ERROR)
- `RunInfo`: Dataclass with run metadata and cancel_event

**API Endpoints**:
- `POST /api/v1/agent/cancel`: Cancel by run_id or session_id
- `GET /api/v1/agent/runs/active`: List active runs

**Usage**:
```python
from omni_agent.core import run_manager, RunStatus

# Register a run
cancel_event = await run_manager.register(run_id, session_id, user_id)

# Pass cancel_event to Agent
agent = Agent(llm_client=llm, tools=tools, cancel_event=cancel_event)

# Cancel from another coroutine
await run_manager.cancel(run_id)

# Cleanup after completion
await run_manager.unregister(run_id, RunStatus.COMPLETED)
```

**Frontend Integration**:
```javascript
// Start streaming
const response = await fetch('/api/v1/agent/run/stream', {...});
const reader = response.body.getReader();

// First event contains run_id
const firstEvent = await reader.read();
const { run_id } = JSON.parse(firstEvent.data);

// Cancel button handler
async function cancelRun() {
    await fetch('/api/v1/agent/cancel', {
        method: 'POST',
        body: JSON.stringify({ run_id })
    });
}
```

### RAG Knowledge Base

PostgreSQL + pgvector based hybrid search system (`src/omni_agent/rag/`):

**Architecture**:
- Document processing: PDF support via pypdf, chunking with overlap
- Embedding: DashScope text-embedding-v4 (1024 dimensions)
- Storage: PostgreSQL with pgvector extension
- Search modes: `hybrid` (semantic + keyword), `semantic`, `keyword`

**Key Components**:
- `rag/database.py`: PostgreSQL + pgvector setup
- `rag/embedding_service.py`: Vector embedding generation
- `rag/document_processor.py`: Document chunking and processing
- `rag/rag_service.py`: Search orchestration

**Tool Integration**: `search_knowledge` tool available to agents when `ENABLE_RAG=true`

## Testing Strategy

**Test Structure**:
- `tests/api/` - API endpoint tests
- `tests/core/` - Core component tests (agent, llm_client, token_manager)
- `tests/tools/` - Tool execution tests
- `tests/services/` - Service layer tests

**Running Tests**:
```bash
# All tests
make test

# With coverage
make test-cov

# Specific module
uv run pytest tests/core/test_agent.py -v

# With output
uv run pytest tests/core/ -v -s
```

## Project Constraints

**IMPORTANT PATHS**:
- Source code: `src/omni_agent/` (NOT `omni_agent/`)
- Tests: `tests/`
- External skills: `./skills/`
- Workspace: `./workspace/` (agent file operations default here)
- Logs: `~/.omni-agent/log/` (agent execution logs)

**Python Import Paths**:
- Always import as: `from omni_agent.core import Agent`
- Never: `from src.omni_agent.core import Agent`
- The `src/` is in the Python path via `pyproject.toml` configuration

**Critical Implementation Details**:
1. **MCP Loading**: Must happen in FastAPI lifespan startup, not per-request
2. **Token Management**: Automatic, but can be configured via Agent constructor
3. **Logging**: Automatic for all agent runs when `enable_logging=True` (default)
4. **Tools**: Base tools + MCP tools + Skills all merged in `get_tools()`
5. **PYTHONPATH**: When running from src/, must rename old `omni_agent/` to avoid conflicts
6. **Session Storage**: Three backends available - File (dev), Redis (production), PostgreSQL (persistent)
7. **Model Names**: Always use `provider/model` format in LLM_MODEL setting

## API Endpoints

**Base URL**: `http://localhost:8000`

**Key Endpoints**:
- `POST /api/v1/agent/run` - Execute agent with task
- `GET /api/v1/tools/` - List all available tools
- `GET /health` - Health check
- `GET /docs` - OpenAPI/Swagger documentation

**Agent Request Format**:
```json
{
  "message": "Task description",
  "workspace_dir": "./workspace",  // optional
  "max_steps": 50                  // optional
}
```

**Response includes**:
- `success`: boolean
- `message`: final agent response
- `steps`: number of steps taken
- `logs`: array of execution logs with token usage and timing

## Logging and Tracing

### AgentLogger (Single Agent Logs)

Located at `~/.omni-agent/log/agent_run_YYYYMMDD_HHMMSS.log`

**Log Events**:
- `STEP`: Step number, token usage statistics, percentage
- `REQUEST`: User message or tool call request
- `RESPONSE`: LLM response with thinking process
- `TOOL_EXECUTION`: Tool name, parameters, result, execution time (ms)
- `COMPLETION`: Final agent message, total steps, summary

**Viewing Logs**:
```bash
# List recent logs
ls -lht ~/.omni-agents/log/ | head -5

# View specific run
cat ~/.omni-agents/log/agent_run_20251113_223233.log
```

### TraceLogger (Multi-Agent Workflow Tracking)

Located at `~/.omni-agent/traces/trace_*.jsonl`

**Use trace_viewer tool** for analysis:
```bash
# List all traces
uv run python -m omni_agent.utils.trace_viewer list

# View detailed trace
uv run python -m omni_agent.utils.trace_viewer view trace_team_20251205_abc123.jsonl

# Visualize workflow dependencies
uv run python -m omni_agent.utils.trace_viewer flow trace_dependency_workflow_20251205_xyz789.jsonl
```

**Trace Information**:
- Workflow lifecycle events (start, end)
- Agent spawn/complete events with nesting depth
- Leader → Member delegation chains
- Task dependency relationships
- Token usage aggregation
- Execution hierarchy visualization

See `docs/TRACING_GUIDE.md` for detailed usage.

## Common Pitfalls

1. **Old Directory Conflicts**: If `omni_agent/` exists at root, rename it (should only be `src/omni_agent/`)
2. **MCP Not Loading**: Check `ENABLE_MCP=true` and verify `initialize_mcp_tools()` is called in lifespan
3. **Import Errors**: Use `uv run` prefix, ensure `PYTHONPATH` includes `src/` if running directly
4. **Token Overflow**: Already handled automatically by TokenManager, but configurable via `token_limit` parameter
5. **Missing Logs**: Check `~/.omni-agent/log/` directory, ensure `enable_logging=True` in Agent constructor
6. **RAG Search Fails**: Verify PostgreSQL + pgvector is installed and `DASHSCOPE_API_KEY` is set
7. **Model Not Found**: Ensure `LLM_MODEL` uses `provider/model` format (e.g., `anthropic/claude-3-5-sonnet-20241022`)
8. **SpawnAgent Depth Error**: Child agents hitting `SPAWN_AGENT_MAX_DEPTH` limit - increase or redesign task delegation


## Documentation

- `README.md` - Complete user guide with examples
- `IMPLEMENTATION_SUMMARY.md` - Detailed implementation notes for Token management, AgentLogger, MCP
- `QUICKSTART.md` - Quick setup guide
- `docs/STREAMING.md` - Streaming output feature documentation
- `docs/TRACING_GUIDE.md` - TraceLogger and trace_viewer usage guide
- `docs/MODEL_STANDARDIZATION.md` - Multi-provider LLM configuration
- `docs/OPENROUTER.md` - OpenRouter integration guide
- `docs/CURL_EXAMPLES.md` - API request examples
- API docs available at `/docs` when server is running

## Available Tools Reference

**Base Tools** (always available):
- `read_file`: Read file contents with optional offset/limit
- `write_file`: Write content to file
- `edit_file`: Edit file via string replacement
- `bash`: Execute shell commands with timeout

**Session Tools** (when `ENABLE_SESSION=true`):
- `session_note`: Store session memory
- `recall_note`: Query session memory

**Skill Tools** (when `ENABLE_SKILLS=true`):
- `get_skill`: Load expert skill guidance on-demand

**SpawnAgent Tool** (when `ENABLE_SPAWN_AGENT=true`):
- `spawn_agent`: Create child agent for delegated tasks

**RAG Tools** (when `ENABLE_RAG=true`):
- `search_knowledge`: Search knowledge base with hybrid/semantic/keyword modes

**Team Tools** (only in Team endpoints):
- `delegate_task_to_member`: Leader delegates task to specific member
- `broadcast_task`: Leader broadcasts task to all members

**MCP Tools** (when `ENABLE_MCP=true`):
- Dynamically loaded from `mcp.json` configuration
- Examples: `web_search_exa`, filesystem tools, database tools, etc.


