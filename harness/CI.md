# CI/CD 设计文档

## 流水线概览

```text
Push/PR -> Lint -> Format Check -> Type Check -> Unit Tests -> Coverage Report
```

### 触发条件

| 事件 | 分支 | 说明 |
|------|------|------|
| push | main | 主分支直接推送 |
| pull_request | main | PR 合并到主分支 |

## 阶段详情

### 1. Lint (ruff check)

- 检查代码质量规则 (E, F, I, N, W, UP, B, C4, SIM)
- 不自动修复，仅报告错误
- 失败则阻断后续阶段

### 2. Format Check (ruff format --check)

- 验证代码格式是否符合规范
- 不修改文件，仅检查
- 开发者应在提交前运行 `make format`

### 3. Type Check (mypy)

- 静态类型检查
- 配置: `disallow_untyped_defs = true` (tests 除外)
- Pydantic mypy 插件启用

### 4. Unit Tests (pytest)

- 运行 `tests/` 下所有测试
- 排除 `tests/integration/` (需要外部服务)
- 使用 `pytest-asyncio` 支持异步测试

### 5. Coverage Report

- 使用 `pytest-cov` 生成覆盖率报告
- 输出到终端 + HTML 报告
- 覆盖率数据上传为 CI Artifact

## Workflow 文件

实际配置: `.github/workflows/ci.yml`

### 矩阵策略

- Python 版本: 3.11, 3.12
- OS: ubuntu-latest

### 缓存策略

- 缓存 uv 包缓存目录
- 按 `uv.lock` 哈希作为缓存 key

## 本地验证

在推送前，开发者应运行:

```bash
make check    # lint + format-check + type-check
make test     # 单元测试
```

等价于 CI 流水线的核心阶段。
