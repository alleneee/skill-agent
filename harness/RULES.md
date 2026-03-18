# 项目规则

## 代码风格

### Ruff 配置

- 行宽: 100 字符
- 目标 Python: 3.11+
- 规则集: E, F, I, N, W, UP, B, C4, SIM
- isort: `omni_agent` 作为 first-party

### 注释规范

- 所有代码注释必须使用中文
- 注释应解释"为什么"而非"做什么"
- 公共 API 必须有 docstring

### 类型标注

- 所有公共函数必须有完整类型标注
- 使用 `from __future__ import annotations` 延迟求值
- Pydantic Model 用于数据结构定义

## 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件 | snake_case | `token_manager.py` |
| 类 | PascalCase | `TokenManager` |
| 函数/方法 | snake_case | `run_agent()` |
| 常量 | UPPER_SNAKE_CASE | `MAX_STEPS` |
| 私有成员 | 前缀下划线 | `_internal_state` |
| Pydantic Model | PascalCase + 后缀 | `AgentRequest`, `TeamConfig` |
| API 端点 | kebab-case | `/api/v1/agent/run` |
| 目录 | snake_case 或 kebab-case (skills) | `core/`, `memory-management/` |

## 导入规范

```python
# 正确
from omni_agent.core import Agent
from omni_agent.tools.base import Tool

# 错误 - 不要使用 src 前缀
from src.omni_agent.core import Agent
```

### 导入顺序 (isort 自动管理)

1. 标准库
2. 第三方库
3. omni_agent 内部模块

### 禁止循环导入

- 使用 `TYPE_CHECKING` 延迟导入解决类型引用
- 通过依赖注入而非直接导入解耦模块

## 依赖管理

### 包管理器

- 使用 `uv` 管理依赖，不使用 pip
- `uv sync` 安装依赖
- `uv run` 执行脚本

### 版本约束策略

- 核心依赖: 指定最低版本 `>=x.y.z`
- 有兼容性问题的依赖: 指定范围 `>=x.y.z,<a.b.c`
- 开发依赖: 放在 `[project.optional-dependencies.dev]`

### 添加依赖流程

1. 在 `pyproject.toml` 的 `dependencies` 或 `optional-dependencies` 中添加
2. 运行 `uv sync` 更新 lock 文件
3. 提交 `pyproject.toml` 和 `uv.lock`

## Git 工作流

### 分支策略

- `main`: 稳定主分支
- `feat/<name>`: 功能开发
- `fix/<name>`: Bug 修复
- `refactor/<name>`: 重构

### Commit 规范

格式: `<type>: <description>`

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 代码重构 |
| `docs` | 文档更新 |
| `test` | 测试相关 |
| `chore` | 构建/工具链 |

- 描述使用中文
- 单行不超过 72 字符
- 必要时在 body 中补充细节

### PR 规范

- 标题遵循 commit 规范
- 描述中包含: 变更内容、测试方式、影响范围
- 至少通过 CI 全部检查
- 大改动需要 Code Review
