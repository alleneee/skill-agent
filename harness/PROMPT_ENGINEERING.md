# Prompt 工程规范

## System Prompt 构建

系统提示由 `SystemPromptBuilder` (`src/omni_agent/core/prompt_builder.py`) 按固定顺序构建：

1. Agent 名称和描述
2. 角色定义 (`<your_role>`)
3. 指令列表 (`<instructions>`)
4. Markdown 格式化说明 (`<output_format>`)
5. 工具使用说明 (`<tool_usage_guidelines>`)
6. Skills 元数据
7. 期望输出格式 (`<expected_output>`)
8. 工作空间信息 (`<workspace_info>`)
9. 时间信息 (`<current_datetime>`)
10. 额外信息 (`<additional_information>`)
11. 自定义章节
12. 额外上下文

禁止绕过 Builder 直接拼接 System Prompt 字符串。

## XML 标签规范

使用 XML 标签组织提示结构，提高 LLM 解析准确性：

```xml
<your_role>
你是一个专业的代码审查助手，擅长发现安全漏洞和性能问题。
</your_role>

<instructions>
- 审查代码时关注安全性、性能和可维护性
- 发现问题时给出具体的修复建议和代码示例
- 按严重程度（高/中/低）分类问题
</instructions>

<expected_output>
以 Markdown 格式输出审查报告，包含：问题列表、修复建议、总结。
</expected_output>
```

规则：
- 每个语义块用专用标签包裹
- 标签名使用 snake_case
- 不嵌套自定义标签超过 2 层
- 自定义章节通过 `SystemPromptConfig.custom_sections` 注入

## 角色定义编写

`role` 字段决定 Agent 的行为基调：

好的实践：
- 明确专业领域和能力边界
- 指定行为风格（严谨/友好/简洁）
- 声明限制（不做什么）

```python
SystemPromptConfig(
    role="你是一个 Python 后端工程师，专注于 FastAPI 和 SQLAlchemy。"
         "你只处理后端相关问题，前端问题应建议用户寻求前端专家帮助。"
         "你的回答简洁直接，优先给出可执行的代码方案。",
)
```

差的实践：
- 角色定义过于宽泛（"你是一个全能助手"）
- 没有能力边界（导致 LLM 乱猜）
- 行为风格不明确

## 指令编写

`instructions` 列表中每条指令应：
- 一条指令只做一件事
- 使用祈使句（"检查..."、"使用..."、"禁止..."）
- 具体可执行，避免模糊表述
- 重要指令放在列表前面

```python
instructions=[
    "文件操作前先用 read_file 确认文件内容",
    "修改代码后运行 bash 执行测试验证",
    "遇到不确定的问题时停止并向用户确认",
    "所有代码修改控制在最小必要范围内",
]
```

## 工具描述对 Prompt 的影响

工具的 `description` 和 `parameters.description` 会注入到 LLM 的上下文中：

- 工具描述过长会占用 Token 预算
- 描述模糊会导致 LLM 误用工具
- 参数描述不清会导致参数传错

通过 `instructions` 属性追加的使用说明会被放入 `<tool_usage_guidelines>` 章节：

```python
@property
def instructions(self) -> str | None:
    return "使用 bash 工具时，命令超时默认 120 秒。长时间命令请先评估必要性。"

@property
def add_instructions_to_prompt(self) -> bool:
    return True
```

## Skills 渐进式披露

Skills 系统实现三层渐进式内容披露：

| 层级 | 内容 | 触发方式 |
|------|------|----------|
| Level 1 | 技能名称 + 一行描述 | System Prompt 自动包含 |
| Level 2 | 完整 SKILL.md 内容 | LLM 调用 `get_skill` 工具 |
| Level 3 | reference/ 目录中的参考文档 | SKILL.md 中的路径引用 |

编写 SKILL.md 的规范：

```markdown
---
name: code-review
description: 代码审查最佳实践和检查清单
---

## 审查维度

1. 安全性：SQL 注入、XSS、认证绕过
2. 性能：N+1 查询、内存泄漏、阻塞调用
3. 可维护性：命名规范、单一职责、测试覆盖
```

Frontmatter 必须包含 `name` 和 `description` 字段。

## 多轮对话上下文管理

Agent 执行循环中的消息结构：

```
[system_prompt]
[user_message]         <- 用户任务
[assistant_message]    <- LLM 响应（可能含 tool_calls）
[tool_result]          <- 工具执行结果
[assistant_message]    <- LLM 继续推理
...循环...
[assistant_message]    <- 最终回答（无 tool_calls）
```

Token 管理策略：
- TokenManager 在每次 LLM 调用前检查总 Token 数
- 超过 `token_limit`（默认 120k）时自动压缩
- 压缩保留所有 user 消息，压缩 assistant+tool 轮次
- 压缩比 50-70%

开发时注意：
- System Prompt 越长，留给对话历史的空间越少
- 工具输出超过 `output_limit` 会被截断
- 压缩后信息有损，关键数据应通过文件持久化而非依赖对话记忆

## SpawnAgent 的 Prompt 设计

子 Agent 通过 `spawn_agent` 工具创建，其 Prompt 由以下字段构成：

- `task`: 子 Agent 要完成的任务描述
- `role`: 子 Agent 的角色定义
- `context`: 父 Agent 传递的上下文信息

编写规范：
- `task` 要自包含，子 Agent 看不到父 Agent 的对话历史
- `role` 明确限定专业范围
- `context` 只传必要信息，子 Agent 有独立 Token 预算（默认 50k）
- 子 Agent 不应再 spawn 子 Agent（虽然技术上支持 3 层嵌套）

## Team 角色 Prompt 设计

Team 模式中 Leader 和 Member 的 Prompt 策略不同：

Leader:
- 分析任务、制定计划
- 决定委派给哪个 Member
- 综合 Member 结果

Member:
- 接收具体任务，独立执行
- 不感知其他 Member 的存在
- 结果返回给 Leader

Member 的 System Prompt 由预定义角色模板生成（researcher/writer/coder/reviewer/analyst）。自定义角色需在 `core/team.py` 中扩展。

## 反模式

| 反模式 | 问题 | 正确做法 |
|--------|------|----------|
| System Prompt 超过 5000 Token | 挤压对话空间 | 精简指令，把细节放到 Skills |
| 指令互相矛盾 | LLM 行为不可预测 | 统一审查所有指令 |
| 工具描述抄代码注释 | 不适合 LLM 理解 | 用自然语言重写 |
| 在 Prompt 中写具体代码 | Token 浪费 | 放到 Skill 或文件 |
| 角色定义 + 指令重复 | 冗余占用 Token | 角色定义管"是什么"，指令管"做什么" |
