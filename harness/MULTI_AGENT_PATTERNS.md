# 多 Agent 模式选型规范

## 四种模式对比

| 维度 | Team | MsgHub | Ralph | SpawnAgent |
|------|------|--------|-------|------------|
| 拓扑 | Leader-Member 树状 | 全连接广播 | 单 Agent 迭代 | 父-子委派 |
| 通信 | Leader 单向委派 | 多向广播 | 无（文件间接） | 单向调用-返回 |
| 适用任务 | 可分解的结构化任务 | 需要多视角讨论 | 需要渐进改进 | 独立子任务 |
| Agent 数量 | 2-6 (Leader + Members) | 2-5 (对等参与者) | 1 (反复执行) | 1+N (父+子) |
| 上下文共享 | Member 不共享 | 全员可见 | 跨迭代通过文件 | 子看不到父历史 |
| Token 开销 | 中（每个 Member 独立） | 高（消息广播） | 低（压缩+缓存） | 低（子 Agent 预算独立） |

## 选型决策树

```text
任务是否可以分解为独立子任务？
├── 是 → 子任务之间是否需要交互？
│   ├── 需要 → 交互是讨论型还是协调型？
│   │   ├── 讨论型（需要多视角碰撞） → MsgHub
│   │   └── 协调型（分工后汇总） → Team
│   └── 不需要 → 子任务是否需要专门角色？
│       ├── 是 → Team（利用预定义角色）
│       └── 否 → SpawnAgent（轻量委派）
└── 否 → 任务是否需要反复迭代改进？
    ├── 是 → Ralph
    └── 否 → 单 Agent 直接执行
```

## Team 模式

### 适用场景

- 任务可拆分为 2-6 个独立子任务
- 子任务需要不同专业角色（研究、编码、审查）
- 需要一个 Leader 综合全局

### 配置

```python
from omni_agent.core import Team

team = Team(
    llm_client=llm,
    members=["researcher", "coder", "reviewer"],
    tools=tools,
)
result = await team.run("实现用户认证模块并审查安全性")
```

### 约束

- Member 之间不通信，只通过 Leader 间接协调
- Leader 每次只能委派给一个 Member
- Member 执行完成后结果返回 Leader
- TraceLogger 记录完整的委派链

### 反模式

- 给单一任务创建 Team（单 Agent 就够了）
- Member 数量超过 6 个（Leader 综合能力下降）
- 让 Member 处理需要其他 Member 结果的任务（应由 Leader 编排顺序）

## MsgHub 模式

### 适用场景

- 需要多角色讨论得出结论（设计评审、方案对比）
- 参与者之间需要看到彼此观点
- 结论通过共识而非单一决策者产生

### 配置

```python
from omni_agent.core import Agent, MsgHub, MsgHubConfig

designer = Agent(llm_client=llm, name="designer", system_prompt="UI 设计师")
developer = Agent(llm_client=llm, name="developer", system_prompt="后端开发者")
pm = Agent(llm_client=llm, name="pm", system_prompt="产品经理")

config = MsgHubConfig(
    max_rounds=6,
    max_steps_per_turn=5,
    announcement="讨论用户认证方案的技术选型",
)

async with MsgHub([designer, developer, pm], config=config) as hub:
    result = await hub.run("设计一个安全且易用的认证系统")
```

### 约束

- 每轮每个 Agent 发言一次（Orchestrator 控制顺序）
- 消息对所有参与者可见（Token 消耗随参与者数量线性增长）
- Agent 发送 `<hub_complete>` 结束讨论
- `max_rounds` 防止无限讨论

### 反模式

- 参与者超过 5 个（Token 爆炸，讨论失焦）
- 没有设 `max_rounds`（可能无限循环）
- 用 MsgHub 做可独立执行的任务（不需要讨论就别讨论）

## Ralph 迭代模式

### 适用场景

- 任务需要渐进式改进（重构代码、完善文档）
- 单次执行无法完成，需要多轮观察-修改-验证
- 结果保存在文件系统中

### 配置

```python
from omni_agent.core import Agent, RalphConfig

agent = Agent(
    llm_client=llm,
    tools=tools,
    ralph=RalphConfig(
        max_iterations=20,
        idle_threshold=3,
    ),
)
result, logs = await agent.run(task="重构 utils 模块，提取公共函数")
```

### 完成条件

| 条件 | 触发方式 |
|------|----------|
| `PROMISE_TAG` | Agent 输出 `<promise>TASK COMPLETE</promise>` |
| `MAX_ITERATIONS` | 达到 `max_iterations` 上限 |
| `IDLE_THRESHOLD` | 连续 N 次迭代无文件变更 |

### Ralph 专用工具

- `get_cached_result`: 获取上一轮工具调用的缓存结果
- `get_working_memory`: 查看跨迭代的工作记忆
- `update_working_memory`: 更新进度、发现、待办
- `signal_completion`: 主动发出完成信号

### 反模式

- 用 Ralph 做不需要迭代的任务
- `max_iterations` 设太大（浪费 Token）
- 不用 `update_working_memory` 记录进度（下一轮会丢失上下文）

## SpawnAgent

### 适用场景

- 父 Agent 遇到可独立处理的子任务
- 子任务需要隔离上下文（避免污染父 Agent）
- 子任务需要专门角色

### 配置

通过 `spawn_agent` 工具调用（LLM 自行决定何时使用）：

```json
{
  "task": "审查 auth.py 的安全性",
  "role": "安全审计员",
  "context": "这是一个 FastAPI 认证模块，使用 JWT",
  "tools": ["read_file", "bash"],
  "max_steps": 15
}
```

### 约束

- 最大嵌套深度: `SPAWN_AGENT_MAX_DEPTH` (默认 3)
- 子 Agent Token 预算: `SPAWN_AGENT_TOKEN_LIMIT` (默认 50,000)
- 子 Agent 默认最大步数: `SPAWN_AGENT_DEFAULT_MAX_STEPS` (默认 15)
- 子 Agent 看不到父 Agent 的对话历史
- 子 Agent 继承父 Agent 的日志和追踪

### 反模式

- 单步任务用 SpawnAgent（直接执行更快）
- 递归 Spawn（A spawn B spawn C spawn D）
- 不限制 `tools` 范围（子 Agent 不需要所有工具）

## 模式组合

支持模式嵌套使用：

- Team Leader 可以使用 SpawnAgent 委派特定任务
- Ralph 循环中可以使用 SpawnAgent 处理子步骤
- MsgHub 参与者可以各自使用工具

禁止：
- MsgHub 内嵌 MsgHub
- Ralph 内嵌 Ralph
- 嵌套层级超过 3 层
