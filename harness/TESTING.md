# 自动测试规范

## 测试分层

| 层级 | 目录 | 范围 | 运行频率 |
|------|------|------|----------|
| Unit | `tests/core/`, `tests/tools/`, `tests/schemas/` | 单个函数/类 | 每次提交 |
| Integration | `tests/integration/` | 多组件协作 | PR 合并前 |
| API | `tests/api/` | HTTP 端点 | PR 合并前 |
| E2E | `tests/e2e/` | 完整用户流程 | 发布前 |

## 目录映射

```text
src/omni_agent/core/agent.py      -> tests/core/test_agent.py
src/omni_agent/core/team.py       -> tests/core/test_team.py
src/omni_agent/core/ralph.py      -> tests/core/test_ralph.py
src/omni_agent/tools/base.py      -> tests/tools/test_base.py
src/omni_agent/api/v1/endpoints/  -> tests/api/v1/
```

## Fixture 规范

### conftest.py 层级

```text
tests/conftest.py           # 全局 fixture (mock LLM, 公共配置)
tests/core/conftest.py      # Core 层 fixture
tests/api/conftest.py       # API 层 fixture (TestClient)
```

### 常用 Fixture 模式

```python
@pytest.fixture
def mock_llm_client():
    """模拟 LLM 客户端，返回固定响应"""
    client = AsyncMock(spec=LLMClient)
    client.call.return_value = {"content": "test response", "tool_calls": []}
    return client

@pytest.fixture
def sample_tools():
    """提供测试用工具集"""
    return [ReadTool(), WriteTool()]

@pytest.fixture
async def agent(mock_llm_client, sample_tools):
    """构造测试用 Agent 实例"""
    return Agent(llm_client=mock_llm_client, tools=sample_tools)
```

## Mock 策略

### LLM 调用

- 始终 mock LLM 调用，不在单元测试中发起真实 API 请求
- 使用 `AsyncMock` 模拟异步调用
- 需要测试多轮对话时，使用 `side_effect` 返回序列响应

### 外部服务

- MCP Server: mock `mcp_loader.py` 中的加载逻辑
- RAG/Embedding: mock `embedding_service.py` 和 `database.py`
- Sandbox: mock `sandbox/manager.py`

### 文件操作

- 使用 `tmp_path` fixture 创建临时目录
- 测试结束后自动清理

## 覆盖率要求

| 模块 | 最低覆盖率 |
|------|-----------|
| `core/agent.py` | 80% |
| `core/team.py` | 70% |
| `core/token_manager.py` | 90% |
| `tools/` | 80% |
| `api/` | 70% |
| 整体 | 60% |

### 覆盖率检查

```bash
make test-cov
# 生成 HTML 报告: htmlcov/index.html
```

## 测试命名和组织

### 命名规范

```python
# 文件名: test_<module>.py
# 类名: Test<Feature>
# 函数名: test_<action>_<condition>_<expected>

class TestTokenManager:
    def test_count_tokens_empty_string_returns_zero(self):
        ...

    def test_summarize_exceeds_limit_compresses_history(self):
        ...

    async def test_check_within_limit_no_compression(self):
        ...
```

### 标记 (Markers)

```python
@pytest.mark.asyncio       # 异步测试
@pytest.mark.integration   # 集成测试 (CI 中可选跳过)
@pytest.mark.slow          # 慢速测试
```

### 运行命令

```bash
# 全部测试
make test

# 仅单元测试 (排除 integration)
uv run pytest -v --ignore=tests/integration

# 指定文件
uv run pytest tests/core/test_agent.py -v

# 指定函数
uv run pytest tests/core/test_agent.py::TestAgent::test_run -v

# 显示输出
uv run pytest -v -s
```
