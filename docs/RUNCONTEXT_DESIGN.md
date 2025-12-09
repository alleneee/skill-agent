# RunContext 设计说明

## 设计理念

`RunContext` 是框架内部的上下文传递机制，**不应该由用户手动创建**。

## 用户 API（推荐使用方式）

用户应该使用独立参数：

```python
# ✅ 推荐：使用独立参数
response = await team.run(
    message="你的任务",
    session_id="user-session-123",
    user_id="user-456",
    max_steps=50
)
```

## 内部实现

框架会自动创建 `RunContext`：

```python
# 在 Team.run() 内部
if run_context is None:
    run_context = RunContext(
        run_id=str(uuid4()),
        session_id=session_id or str(uuid4()),
        user_id=user_id,
    )
```

## RunContext 的真正用途

`RunContext` 主要用于**框架内部的层级传递**：

1. **Team → Member Agent**
   ```python
   # Team.run() 创建 RunContext
   run_context = RunContext(run_id=..., session_id=..., user_id=...)

   # 通过闭包传递给 member
   async def delegate_task_to_member(member_id: str, task: str):
       result = await self._run_member(
           member_config,
           task,
           session_id=run_context.session_id  # 使用闭包捕获的 run_context
       )
   ```

2. **保持上下文一致性**
   - 所有 member agents 共享同一个 session_id
   - 所有操作都关联到同一个 run_id
   - session_state 和 dependencies 在整个调用链中保持一致

3. **显式而非隐式**
   - 不依赖全局变量或线程局部存储
   - 显式传递上下文，易于追踪和调试

## 高级用法（框架内部）

`run_context` 参数主要用于框架内部调用：

```python
# 框架内部：Team 调用 member Agent
member_agent = Agent(...)
member_response = await member_agent.run(
    message=task,
    run_context=run_context  # 传递父级的 run_context
)
```

## 总结

- **用户视角**：只需传递 `session_id`, `user_id` 等参数
- **框架视角**：使用 `RunContext` 在内部优雅地传递上下文
- **设计哲学**：简单的用户 API + 强大的内部机制

这种设计参考了 [agno](https://github.com/agno-ai/agno) 的最佳实践。
