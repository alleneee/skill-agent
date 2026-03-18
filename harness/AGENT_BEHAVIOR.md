# Agent 行为规范

## 执行循环规范

### 参数约束

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_steps` | 50 | 单次运行最大步数，防止死循环 |
| `token_limit` | 120,000 | Token 上限，超过自动压缩 |
| `max_tokens` | 按 Provider 自适应 | LLM 单次响应最大 Token |

### 执行流程

1. 接收用户消息
2. TokenManager 检查 Token 用量
3. 若超过 `token_limit`，压缩历史消息
4. 调用 LLM 生成响应
5. 若有 tool_calls，执行工具并记录结果
6. 循环直到：LLM 返回纯文本响应 / 达到 `max_steps` / 收到取消信号

### 终止条件

- LLM 返回无 tool_calls 的响应 -> 正常完成
- 步数达到 `max_steps` -> 超时终止，返回已有结果
- `cancel_event` 触发 -> 取消终止，清理未完成消息
- Token 压缩后仍超限 -> 异常终止

## 工具调用约束

### 权限控制

- 文件操作工具仅在 `workspace_dir` 范围内执行
- Sandbox 模式下，bash 命令在隔离容器中运行
- SpawnAgent 受 `SPAWN_AGENT_MAX_DEPTH` 限制嵌套深度

### 超时管理

- Bash 工具默认超时: 120 秒
- MCP 工具调用超时: 由 MCP Server 端控制
- 工具执行时间记录在 AgentLogger 中

### 错误处理

- 工具执行失败 -> 将错误信息作为 tool_result 返回给 LLM
- LLM 自行决定是否重试或换用其他工具
- 连续失败不自动重试，由 LLM 判断

## 多 Agent 协作规则

### Team 委派

- Leader 通过 `delegate_task_to_member` 分配任务
- Member 独立执行，不共享 Token 预算
- Member 结果返回给 Leader 综合
- 预定义角色: researcher, writer, coder, reviewer, analyst

### MsgHub 广播

- 每个 Agent 通过 `observe()` 接收他人消息
- `execute_turn()` 执行一轮讨论
- Orchestrator 决定下一个发言者（默认轮询）
- Agent 发送 `<hub_complete>` 信号结束讨论

### SpawnAgent

- 子 Agent 继承父 Agent 的日志和追踪
- 最大嵌套深度: `SPAWN_AGENT_MAX_DEPTH` (默认 3)
- 子 Agent Token 限制: `SPAWN_AGENT_TOKEN_LIMIT` (默认 50,000)
- 子 Agent 默认最大步数: `SPAWN_AGENT_DEFAULT_MAX_STEPS` (默认 15)

## 错误处理和容错策略

### LLM 调用失败

- 网络超时 -> 自动重试（指数退避）
- API 限流 -> 等待后重试
- 无效响应 -> 记录日志，返回错误信息

### Token 溢出

- TokenManager 自动检测并压缩
- 压缩策略: 保留所有 user 消息，压缩 agent 执行轮次
- 压缩比: 50-70%

### 工具执行异常

- 捕获所有异常，转为错误信息返回 LLM
- 不中断执行循环
- 在 AgentLogger 中记录完整错误栈

## 安全边界

### 文件访问

- Agent 文件操作限制在 `workspace_dir` 内
- 禁止访问系统敏感目录
- 文件工具对路径做规范化和校验

### Sandbox 隔离

- `ENABLE_SANDBOX=true` 时，bash 命令在 Docker 容器中执行
- 沙箱实例有 TTL 限制 (默认 1 小时)
- 最大并发实例数: `SANDBOX_MAX_INSTANCES` (默认 100)

### 输入校验

- 用户输入经 Pydantic Model 校验
- 工具参数经 JSON Schema 校验
- LLM 返回的 tool_calls 参数做类型检查
