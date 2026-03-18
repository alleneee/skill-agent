# 自动验证清单

## 开发前验证

### 环境检查

```bash
# Python 版本 (需要 3.11+)
python --version

# uv 安装
uv --version

# 依赖安装
uv sync

# 环境变量配置
cat .env | grep -E "^(LLM_|ENABLE_)" | head -10
```

### 必要配置

- [ ] `.env` 文件存在且包含 `LLM_API_KEY`
- [ ] `LLM_MODEL` 使用 `provider/model` 格式
- [ ] `mcp.json` 存在且格式正确 (如启用 MCP)
- [ ] PostgreSQL + pgvector 运行中 (如启用 RAG)

## 提交前验证

```bash
# 一键检查 (lint + format + type)
make check

# 运行单元测试
make test

# 等价于:
uv run ruff check .
uv run ruff format --check .
uv run mypy src/omni_agent
uv run pytest -v --ignore=tests/integration
```

### 提交检查项

- [ ] `make check` 全部通过
- [ ] `make test` 全部通过
- [ ] 新增代码有对应测试
- [ ] 文档已更新 (如 API 变更)
- [ ] Commit 消息符合规范

## CI 验证

### 流水线阶段

| 阶段 | 命令 | 阻断级别 |
|------|------|----------|
| Lint | `ruff check .` | 失败阻断 |
| Format | `ruff format --check .` | 失败阻断 |
| Type Check | `mypy src/omni_agent` | 失败阻断 |
| Unit Tests | `pytest --ignore=tests/integration` | 失败阻断 |
| Coverage | `pytest --cov` | 报告，不阻断 |

### CI 配置文件

- `.github/workflows/ci.yml`

## 部署前验证

### 配置检查

```bash
# 验证必要环境变量
uv run python -c "from omni_agent.core.config import settings; print(settings.model_dump())"

# 健康检查端点
curl http://localhost:8000/health
```

### 检查项

- [ ] 所有必要环境变量已设置
- [ ] LLM API 连通性正常
- [ ] MCP Server 全部启动成功
- [ ] 健康检查返回 200
- [ ] 日志目录可写 (`~/.omni-agent/log/`)

## Agent 运行时验证

### Token 溢出检测

- TokenManager 在每次 LLM 调用前自动检查
- 超过 `token_limit` (120k) 时自动压缩
- 压缩失败时记录告警日志

### 死循环检测

- `max_steps` 限制最大执行步数 (默认 50)
- AgentLogger 记录每步 Token 用量
- 连续相同工具调用检测（Ralph 模式 idle_threshold）

### 运行状态监控

```bash
# 查看活跃运行
curl http://localhost:8000/api/v1/agent/runs/active

# 取消运行
curl -X POST http://localhost:8000/api/v1/agent/cancel \
  -H "Content-Type: application/json" \
  -d '{"run_id": "<run_id>"}'
```

### 日志检查

```bash
# 最近的运行日志
ls -lht ~/.omni-agent/log/ | head -5

# 追踪日志
ls -lht ~/.omni-agent/traces/ | head -5

# 查看特定追踪
uv run python -m omni_agent.utils.trace_viewer list
```
