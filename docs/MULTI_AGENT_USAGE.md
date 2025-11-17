# 多 Agent 协调系统使用指南

## 概述

本项目实现了一个灵活的多 Agent 协调系统,借鉴了 [Agno](https://github.com/agno-org/agno) 项目的优秀设计,支持多个 AI Agent 协作完成复杂任务。

## 核心特性

- **多种协调策略**: Leader-Worker, Broadcast, Sequential, Round-Robin
- **成员交互共享**: 支持成员间查看彼此的输入输出
- **灵活的工具分配**: 不同成员可配置不同的工具集
- **完整的执行日志**: 记录每个步骤的详细信息
- **共享状态管理**: 成员间可共享任务上下文

## 协调策略说明

### 1. Leader-Worker (领导者-工作者)

**适用场景**: 复杂任务需要智能分解和汇总

**工作流程**:
```
1. Coordinator 分析任务
2. 制定执行计划并分配给成员
3. 成员执行各自的子任务
4. Coordinator 汇总所有结果
```

**示例代码**:
```python
from fastapi_agent.core import Agent, AgentTeam, CoordinationStrategy

# 创建协调者
coordinator = Agent(
    llm_client=llm_client,
    name="Coordinator",
    system_prompt="你是团队协调者,负责分析任务并合理分工"
)

# 创建成员
researcher = Agent(llm_client=llm_client, name="Researcher", tools=[ReadTool()])
writer = Agent(llm_client=llm_client, name="Writer", tools=[WriteTool()])

# 创建团队
team = AgentTeam(
    members=[researcher, writer],
    coordinator=coordinator,
    strategy=CoordinationStrategy.LEADER_WORKER,
    share_interactions=True
)

# 执行任务
result = team.run("研究 Python 异步编程并写一篇技术文章")
print(result.final_output)
```

### 2. Broadcast (广播)

**适用场景**: 需要多角度分析的任务

**工作流程**:
```
1. 将相同任务发送给所有成员
2. 成员并行或顺序执行
3. 汇总所有成员的输出
```

**示例代码**:
```python
# 创建多个分析师
analysts = [
    Agent(llm_client=llm_client, name="Performance Analyst"),
    Agent(llm_client=llm_client, name="Security Analyst"),
    Agent(llm_client=llm_client, name="UX Analyst")
]

# 创建团队
team = AgentTeam(
    members=analysts,
    strategy=CoordinationStrategy.BROADCAST
)

# 执行任务
result = team.run("分析这个 API 设计方案")
```

### 3. Sequential (顺序)

**适用场景**: Pipeline 式的任务处理流程

**工作流程**:
```
1. Member 1 处理原始任务
2. Member 2 处理 Member 1 的输出
3. Member 3 处理 Member 2 的输出
...
返回最后一个成员的输出
```

**示例代码**:
```python
# 创建 pipeline 成员
team = AgentTeam(
    members=[
        Agent(llm_client=llm_client, name="Researcher"),
        Agent(llm_client=llm_client, name="Writer"),
        Agent(llm_client=llm_client, name="Reviewer")
    ],
    strategy=CoordinationStrategy.SEQUENTIAL
)

# 执行任务
result = team.run("创建一篇关于 AI 的文章")
```

### 4. Round-Robin (轮询)

**适用场景**: 均衡分配独立子任务

**工作流程**:
```
按顺序将任务分配给各个成员
```

## API 使用

### REST API 端点

**POST /api/v1/team/run**

```bash
curl -X POST "http://localhost:8000/api/v1/team/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "研究 Python 异步编程并写技术文章",
    "strategy": "leader_worker",
    "members": ["researcher", "writer", "reviewer"],
    "coordinator_role": "coordinator",
    "share_interactions": true,
    "max_steps": 30
  }'
```

**响应**:
```json
{
  "success": true,
  "final_output": "最终的文章内容...",
  "member_outputs": {
    "Researcher": "研究结果...",
    "Writer": "撰写的文章...",
    "Reviewer": "审阅意见..."
  },
  "interactions": [...],
  "steps": 5,
  "logs": [...]
}
```

### 可用角色

系统预定义了以下角色,每个角色有特定的提示词和工具集:

- **coordinator**: 协调者,负责任务分析和计划
- **researcher**: 研究员,擅长信息收集
- **writer**: 写作专家,擅长文档编写
- **coder**: 编程专家,擅长代码编写
- **reviewer**: 审阅专家,擅长质量检查
- **analyst**: 数据分析专家

### 查询可用策略

**GET /api/v1/team/strategies**

```bash
curl "http://localhost:8000/api/v1/team/strategies"
```

## 代码示例

### 完整示例

参考 `examples/team_demo.py`:

```bash
# 运行演示
uv run python examples/team_demo.py
```

### 自定义成员

```python
from fastapi_agent.tools import ReadTool, WriteTool, BashTool

# 创建自定义工具集
research_tools = [ReadTool(), BashTool()]
writing_tools = [WriteTool(), ReadTool()]

# 创建自定义成员
custom_researcher = Agent(
    llm_client=llm_client,
    name="CustomResearcher",
    system_prompt="你是专业的研究员...",
    tools=research_tools,
    max_steps=10
)

custom_writer = Agent(
    llm_client=llm_client,
    name="CustomWriter",
    system_prompt="你是专业的技术写作专家...",
    tools=writing_tools,
    max_steps=10
)

# 使用自定义成员
team = AgentTeam(
    members=[custom_researcher, custom_writer],
    strategy=CoordinationStrategy.SEQUENTIAL
)
```

### 启用成员交互共享

```python
team = AgentTeam(
    members=[agent1, agent2, agent3],
    strategy=CoordinationStrategy.LEADER_WORKER,
    coordinator=coordinator,
    share_interactions=True  # 启用交互共享
)

result = team.run("复杂任务...")

# 查看交互历史
for interaction in result.interactions:
    print(f"{interaction.member_name}: {interaction.input_message} -> {interaction.output_message}")
```

## 日志和调试

团队执行日志保存在: `~/.fastapi-agent/log/team_run_YYYYMMDD_HHMMSS.log`

日志包含:
- TEAM_INIT: 团队初始化
- MEMBER_INTERACTION: 成员交互记录
- TEAM_RUN_START: 任务开始
- TEAM_RUN_COMPLETE: 任务完成
- TEAM_RUN_ERROR: 错误信息

## 最佳实践

### 1. 选择合适的策略

- **简单任务**: Sequential 或 Broadcast
- **复杂任务**: Leader-Worker
- **需要多角度分析**: Broadcast
- **流水线处理**: Sequential

### 2. 合理设置 max_steps

- 单个成员: 5-10 步
- 团队总步数: 20-50 步

### 3. 工具分配原则

- 只给需要的成员分配工具
- 避免所有成员都有相同的工具
- Coordinator 通常不需要工具

### 4. 提示词设计

- 明确每个成员的职责
- 让成员知道团队协作的目标
- 如果启用 `share_interactions`,提示成员参考其他成员的输出

## 架构参考

本实现参考了 Agno 项目的设计:
- Team 类: `/Users/niko/agno/libs/agno/agno/team/team.py`
- Workflow Step: `/Users/niko/agno/libs/agno/agno/workflow/step.py`

详细设计文档: `docs/MULTI_AGENT_DESIGN.md`

## 常见问题

**Q: 如何限制团队执行时间?**
A: 通过设置 `max_steps` 参数来限制最大执行步数。

**Q: 成员交互共享会影响性能吗?**
A: 会略微增加 token 使用量,但提高了协作质量。

**Q: 可以嵌套 Team 吗?**
A: 当前版本暂不支持,将在后续版本实现。

**Q: 如何查看详细的执行过程?**
A: 查看日志文件或设置 `enable_logging=True` 并检查 `result.logs`。

## 下一步计划

- [ ] 支持嵌套 Team (Team 中包含 Team)
- [ ] 支持并发执行 (真正的并行)
- [ ] 支持流式输出
- [ ] 动态成员添加/移除
- [ ] 更多预定义角色
- [ ] Web UI 界面

## 贡献

欢迎提交 Issue 和 PR 来改进多 Agent 协调系统!
