# 多 Agent 协调系统设计文档

## 1. 设计目标

基于 agno 项目的优秀实践,为本项目实现一个轻量级但功能完整的多 agent 协调系统。

### 核心目标
- 支持多个 Agent 协作完成复杂任务
- 提供灵活的任务分配和协调机制
- 保持与现有架构的兼容性
- 支持流式和非流式两种执行模式

## 2. 架构设计

### 2.1 核心组件

```
AgentTeam (协调器)
├── members: List[Agent]           # 团队成员
├── coordinator: Agent             # 协调者(可选)
├── strategy: CoordinationStrategy # 协调策略
└── session_state: Dict[str, Any]  # 共享状态
```

### 2.2 协调策略

#### 策略 1: Leader-Worker (领导者-工作者)
- 由 coordinator agent 分析任务并分配给合适的 worker
- coordinator 汇总结果并生成最终响应
- 适用场景: 复杂任务需要智能分解和汇总

#### 策略 2: Round-Robin (轮询)
- 按顺序将任务分配给各个 agent
- 适用场景: 子任务相对独立且均衡

#### 策略 3: Broadcast (广播)
- 将任务发送给所有 agent
- 收集所有响应后进行汇总
- 适用场景: 需要多角度分析的任务

#### 策略 4: Sequential (顺序)
- 按照定义的顺序,将前一个 agent 的输出作为下一个的输入
- 适用场景: Pipeline 式的任务处理

## 3. 详细设计

### 3.1 AgentTeam 类

```python
from enum import Enum
from typing import List, Dict, Any, Optional, Union, Iterator
from dataclasses import dataclass

class CoordinationStrategy(Enum):
    LEADER_WORKER = "leader_worker"
    ROUND_ROBIN = "round_robin"
    BROADCAST = "broadcast"
    SEQUENTIAL = "sequential"

@dataclass
class AgentTeam:
    """多 Agent 协调器"""

    # 团队成员
    members: List[Agent]

    # 协调策略
    strategy: CoordinationStrategy = CoordinationStrategy.LEADER_WORKER

    # 协调者 (仅在 LEADER_WORKER 策略时使用)
    coordinator: Optional[Agent] = None

    # 团队名称
    name: str = "AgentTeam"

    # 共享会话状态
    shared_state: Optional[Dict[str, Any]] = None

    # 是否启用成员交互共享
    share_interactions: bool = False

    # 最大步数
    max_steps: int = 50

    # 是否启用日志
    enable_logging: bool = True

    def run(
        self,
        message: str,
        workspace_dir: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行团队任务 (非流式)"""
        pass

    def run_stream(
        self,
        message: str,
        workspace_dir: Optional[str] = None,
        **kwargs
    ) -> Iterator[Dict[str, Any]]:
        """执行团队任务 (流式)"""
        pass
```

### 3.2 任务分配流程

#### Leader-Worker 策略流程:
```
1. Coordinator 分析任务
   ├─ 识别需要哪些成员参与
   ├─ 为每个成员生成子任务
   └─ 确定执行顺序

2. 执行子任务
   ├─ 按照计划调用相应成员
   ├─ 传递必要的上下文和状态
   └─ 收集每个成员的输出

3. Coordinator 汇总结果
   ├─ 整合所有成员的输出
   ├─ 生成最终响应
   └─ 更新共享状态
```

#### Broadcast 策略流程:
```
1. 将任务发送给所有成员
2. 并发或顺序执行
3. 收集所有响应
4. 汇总生成最终结果
```

#### Sequential 策略流程:
```
1. Member 1 处理原始任务
2. Member 2 处理 Member 1 的输出
3. Member 3 处理 Member 2 的输出
...
n. 返回最后一个成员的输出
```

### 3.3 成员交互记录

当 `share_interactions=True` 时:

```python
@dataclass
class MemberInteraction:
    """成员交互记录"""
    member_name: str
    input: str
    output: str
    timestamp: str
    metadata: Dict[str, Any]

# 在执行过程中维护交互历史
interactions: List[MemberInteraction] = []
```

### 3.4 共享状态管理

```python
# 初始化共享状态
shared_state = {
    "task_context": {},      # 任务上下文
    "member_outputs": {},    # 成员输出历史
    "coordination_plan": {}, # 协调计划
    "custom_data": {}        # 自定义数据
}

# 成员可以读写共享状态
# 每个成员的 Agent 可以通过工具访问 shared_state
```

## 4. 实现计划

### 4.1 第一阶段: 核心功能
- [ ] 实现 `AgentTeam` 基础类
- [ ] 实现 Leader-Worker 策略
- [ ] 实现基础的任务分配和执行
- [ ] 支持共享状态

### 4.2 第二阶段: 增强功能
- [ ] 实现其他协调策略 (Round-Robin, Broadcast, Sequential)
- [ ] 支持成员交互共享
- [ ] 支持流式输出
- [ ] 添加详细日志

### 4.3 第三阶段: 高级功能
- [ ] 支持嵌套 Team (Team 中包含 Team)
- [ ] 动态成员添加/移除
- [ ] 协调策略的动态切换
- [ ] 性能优化和并发执行

## 5. 文件结构

```
src/fastapi_agent/
├── core/
│   ├── agent_team.py          # AgentTeam 核心类
│   ├── coordination.py        # 协调策略实现
│   └── team_logger.py         # 团队日志
├── tools/
│   └── team_tools.py          # 团队相关工具 (访问共享状态等)
├── api/
│   └── v1/
│       └── team.py            # Team API 端点
└── tests/
    └── core/
        └── test_agent_team.py # 团队测试
```

## 6. API 设计

### POST /api/v1/team/run

```json
{
  "message": "任务描述",
  "strategy": "leader_worker",
  "members": ["agent1", "agent2", "agent3"],
  "coordinator": "coordinator_agent",
  "share_interactions": true,
  "workspace_dir": "./workspace",
  "max_steps": 50
}
```

响应:
```json
{
  "success": true,
  "final_output": "最终结果",
  "member_outputs": {
    "agent1": "...",
    "agent2": "..."
  },
  "interactions": [...],
  "steps": 15,
  "logs": [...]
}
```

## 7. 与现有架构的集成

### 7.1 复用现有组件
- 使用现有的 `Agent` 类作为团队成员
- 复用 `TokenManager` 进行 token 管理
- 复用 `AgentLogger` 进行日志记录
- 复用现有的 Tool 系统

### 7.2 扩展点
- 在 `Agent` 类中添加 `team_context` 属性
- 创建新的 `TeamSharedStateTool` 工具
- 扩展日志格式以支持团队级别的日志

## 8. 示例用法

```python
from fastapi_agent.core import Agent, AgentTeam
from fastapi_agent.core.coordination import CoordinationStrategy

# 创建成员
researcher = Agent(
    llm_client=llm,
    tools=[SearchTool(), ReadTool()],
    name="Researcher"
)

writer = Agent(
    llm_client=llm,
    tools=[WriteTool()],
    name="Writer"
)

reviewer = Agent(
    llm_client=llm,
    tools=[],
    name="Reviewer"
)

# 创建协调者
coordinator = Agent(
    llm_client=llm,
    tools=[],
    name="Coordinator",
    system_prompt="你是团队协调者,负责分析任务并分配给合适的成员"
)

# 创建团队
team = AgentTeam(
    members=[researcher, writer, reviewer],
    coordinator=coordinator,
    strategy=CoordinationStrategy.LEADER_WORKER,
    share_interactions=True
)

# 执行任务
result = team.run(
    "研究 Python 异步编程并写一篇技术文章,然后审阅"
)
```

## 9. 参考资源

- Agno Team 实现: `/Users/niko/agno/libs/agno/agno/team/team.py`
- Agno Workflow Step: `/Users/niko/agno/libs/agno/agno/workflow/step.py`
