# 评估规范

## 评估框架

项目内置评估框架位于 `src/omni_agent/eval/`，用于验证 Agent 行为质量。

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `EvalRunner` | `eval/runner.py` | 运行评估用例，创建隔离环境 |
| `EvalDataset` | `eval/dataset.py` | 加载和管理评估用例集 |
| `EvalCase` | `eval/dataset.py` | 单个评估用例定义 |
| `BaseGrader` | `eval/grader.py` | 评分基类 |
| `OutcomeGrader` | `eval/grader.py` | 基于结果的评分器 |
| `IsolatedWorkspace` | `eval/isolation.py` | 隔离文件系统环境 |
| `EvalReport` | `eval/report.py` | 评估结果报告 |
| `EvalConfig` | `eval/config.py` | 评估全局配置 |

## 评估用例格式

用例文件位于 `evals/` 目录，使用 YAML 格式：

```yaml
- id: "tool_read_file_001"
  task: "Read the file app.py and tell me what functions are defined."
  tags: ["tool", "read", "quick"]
  max_steps: 5
  timeout: 30
  setup:
    files:
      "app.py": |
        def hello():
            return "world"
        def add(a, b):
            return a + b
  grading:
    type: "outcome"
    checks:
      - result_contains: "hello"
      - result_contains: "add"
```

### 字段说明

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 用例唯一标识，格式: `<category>_<tool>_<seq>` |
| `task` | string | 是 | Agent 要执行的任务描述 |
| `tags` | list[string] | 否 | 标签，用于筛选运行 |
| `max_steps` | int | 否 | 该用例最大步数 |
| `timeout` | int | 否 | 超时秒数 |
| `setup.files` | dict | 否 | 预创建的文件 {路径: 内容} |
| `setup.dirs` | list | 否 | 预创建的目录 |
| `grading` | dict | 是 | 评分配置 |

### 评分检查类型

| 检查 | 说明 | 示例 |
|------|------|------|
| `result_contains` | 最终结果包含指定文本 | `result_contains: "hello"` |
| `file_exists` | 指定文件存在 | `file_exists: "output.py"` |
| `file_contains` | 指定文件包含指定文本 | `file_contains: ["output.py", "def main"]` |
| `file_not_contains` | 指定文件不包含指定文本 | `file_not_contains: ["config.py", "DEBUG = False"]` |
| `result_matches` | 最终结果匹配正则表达式 | `result_matches: "(?i)error"` |
| `file_matches` | 指定文件内容匹配正则表达式 | `file_matches: ["report.txt", "(?i)sql.?inject"]` |

## 评估用例分类

```text
evals/
├── tool_usage/        # 工具使用能力 (15 cases)
│   └── cases.yaml     # read/write/edit/bash + 组合调用
├── multi_step/        # 多步推理能力 (11 cases)
│   └── cases.yaml     # 多步工具调用、重构、调试、数据处理
├── code_generation/   # 代码生成能力 (10 cases)
│   └── cases.yaml     # 算法、设计模式、Bug修复、异步编程
├── reasoning/         # 推理与分析 (8 cases)
│   └── cases.yaml     # 日志分析、代码审查、数学推理、配置审计
├── safety/            # 安全边界 (10 cases)
│   └── cases.yaml     # 路径逃逸、危险命令、prompt injection
└── efficiency/        # 效率基准 (7 cases)
    └── cases.yaml     # 最少步骤完成、针搜索、批量操作
```

### 用例命名规范

```
<category>_<subcategory>_<seq>

tool_read_file_001      # 工具 - 读文件 - 第1个
tool_bash_002           # 工具 - bash - 第2个
multi_step_refactor_001 # 多步 - 重构 - 第1个
safety_path_escape_001  # 安全 - 路径逃逸 - 第1个
```

## 运行评估

```bash
uv run python -m omni_agent.eval
uv run python -m omni_agent.eval --tags tool
uv run python -m omni_agent.eval --case-id tool_read_file_001
```

## 隔离环境

每个评估用例在 `IsolatedWorkspace` 中运行：

- 创建临时目录作为 `workspace_dir`
- 根据 `setup.files` 和 `setup.dirs` 预创建文件
- Agent 的文件工具被限制在该临时目录
- 用例结束后自动清理

## 编写评估用例的规范

### 必须覆盖的维度

新增工具时：
- 正常使用：参数正确，预期结果
- 参数缺失：必填参数未提供
- 参数非法：类型错误、值越界
- 边界条件：空文件、大文件、特殊字符

新增 Agent 能力时：
- 基础能力：单步完成
- 组合能力：多步协作
- 错误恢复：遇到失败后的处理

### 评分粒度

| 场景 | 推荐检查方式 |
|------|-------------|
| 生成文件 | `file_exists` + `file_contains` |
| 修改文件 | `file_contains` + `file_not_contains` |
| 信息提取 | `result_contains` |
| 代码执行 | `file_contains`（检查输出文件） |

### 超时和步数设置

| 任务复杂度 | max_steps | timeout |
|-----------|-----------|---------|
| 单步工具调用 | 3-5 | 30s |
| 多步简单任务 | 10-15 | 60s |
| 复杂推理任务 | 20-30 | 120s |

## 自定义 Grader

继承 `BaseGrader` 实现自定义评分逻辑：

```python
from omni_agent.eval.grader import BaseGrader, GradeResult

class CodeQualityGrader(BaseGrader):
    async def grade(self, case, workspace, result):
        target = workspace / "output.py"
        if not target.exists():
            return GradeResult.failure("output.py not found")

        code = target.read_text()

        import subprocess
        proc = subprocess.run(
            ["ruff", "check", str(target)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return GradeResult.failure(f"Lint errors: {proc.stdout}")

        return GradeResult.success("Code passes lint")
```

## 评估指标

### 核心指标

| 指标 | 计算方式 | 基准 |
|------|----------|------|
| 通过率 | passed / total | >= 90% (tool_usage) |
| 平均步数 | sum(steps) / total | 接近 max_steps 的 50% |
| 平均耗时 | sum(duration) / total | < timeout 的 50% |
| Token 效率 | sum(tokens) / passed | 越低越好 |

### CI 集成

评估可在 CI 中运行，但注意：
- 需要真实 LLM API Key（不能 mock）
- 耗时较长，建议仅在 release 前运行
- 通过 `--tags quick` 筛选快速用例做冒烟测试
