# 流式输出功能文档

## 概述

FastAPI Agent 现在支持服务器发送事件 (SSE) 的流式输出功能，让你可以实时查看 agent 的执行过程。

## 功能特性

- ✅ **实时思考流** - 查看 agent 的思考过程
- ✅ **内容流式输出** - 逐字输出 agent 的回复
- ✅ **工具调用事件** - 实时显示工具的调用和结果
- ✅ **步骤进度** - 追踪 agent 执行的每个步骤
- ✅ **Token 使用情况** - 实时监控 token 使用量

## API 端点

### 流式端点

```
POST /api/v1/agent/run/stream
```

### 请求格式

```json
{
  "message": "你的任务描述",
  "max_steps": 50  // 可选，默认 50
}
```

### 响应格式

使用 Server-Sent Events (SSE) 格式，每个事件包含：

```
data: {"type": "event_type", "data": {...}}
```

## 事件类型

### 1. `log_file`
日志文件路径信息

```json
{
  "type": "log_file",
  "data": {
    "log_file": "/home/user/.fastapi-agent/log/agent_run_20251114_114221.log"
  }
}
```

### 2. `step`
步骤开始信息

```json
{
  "type": "step",
  "data": {
    "step": 1,
    "max_steps": 50,
    "tokens": 154,
    "token_limit": 120000
  }
}
```

### 3. `thinking`
Agent 思考过程（增量）

```json
{
  "type": "thinking",
  "data": {
    "delta": "用户要求我..."
  }
}
```

### 4. `content`
Agent 回复内容（增量）

```json
{
  "type": "content",
  "data": {
    "delta": "你好！"
  }
}
```

### 5. `tool_call`
工具调用开始

```json
{
  "type": "tool_call",
  "data": {
    "tool": "bash",
    "arguments": {
      "command": "date '+%A'"
    }
  }
}
```

### 6. `tool_result`
工具执行结果

```json
{
  "type": "tool_result",
  "data": {
    "tool": "bash",
    "success": true,
    "content": "Friday",
    "error": null,
    "execution_time": 0.01
  }
}
```

### 7. `done`
任务完成

```json
{
  "type": "done",
  "data": {
    "message": "最终的回复内容",
    "steps": 2,
    "reason": "completed"
  }
}
```

### 8. `error`
错误事件

```json
{
  "type": "error",
  "data": {
    "message": "错误描述",
    "reason": "max_steps_reached"
  }
}
```

## 使用示例

### Python (httpx)

```python
import httpx
import json
import asyncio

async def stream_agent():
    url = "http://localhost:8000/api/v1/agent/run/stream"
    payload = {
        "message": "你好，请介绍一下自己",
        "max_steps": 10
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    event_type = event["type"]
                    event_data = event["data"]

                    if event_type == "content":
                        print(event_data["delta"], end="", flush=True)
                    elif event_type == "done":
                        print("\n完成!")
                        break

asyncio.run(stream_agent())
```

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run/stream" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "max_steps": 5}' \
  --no-buffer
```

### JavaScript/TypeScript (fetch)

```javascript
async function streamAgent(message) {
  const response = await fetch('http://localhost:8000/api/v1/agent/run/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6));

        if (event.type === 'content') {
          process.stdout.write(event.data.delta);
        } else if (event.type === 'done') {
          console.log('\n完成!');
        }
      }
    }
  }
}

streamAgent('你好，请介绍一下自己');
```

## 架构说明

### 1. LLM Client 层

`LLMClient.generate_stream()` 方法：
- 发送 `stream=True` 参数到 LLM API
- 解析 SSE 流式响应
- 生成增量事件（thinking_delta, content_delta, tool_use）

### 2. Agent 层

`Agent.run_stream()` 方法：
- 协调整个执行流程
- 调用 LLM 流式生成
- 执行工具并流式返回结果
- 管理消息历史和状态

### 3. API 层

`/run/stream` endpoint：
- 接收用户请求
- 调用 agent 流式方法
- 将事件转换为 SSE 格式
- 返回 StreamingResponse

## 性能优化建议

1. **设置合理的超时时间**
   ```python
   httpx.AsyncClient(timeout=120.0)  # 2分钟超时
   ```

2. **处理网络中断**
   ```python
   try:
       async for event in stream:
           process_event(event)
   except httpx.ReadTimeout:
       print("连接超时，请重试")
   ```

3. **缓冲输出**
   - 前端显示时考虑使用缓冲区
   - 避免每个字符都触发 UI 重绘

## 对比普通 API

| 特性 | 普通 API (`/run`) | 流式 API (`/run/stream`) |
|------|------------------|-------------------------|
| 响应方式 | 等待完成后返回 | 实时流式输出 |
| 用户体验 | 等待时间长 | 实时反馈，体验好 |
| 适用场景 | 后台任务、批处理 | 交互式应用、聊天界面 |
| 实现复杂度 | 简单 | 需要处理 SSE |
| Token 监控 | 事后查看 | 实时监控 |

## 故障排查

### 问题：没有收到流式输出

**可能原因**：
1. Nginx/代理服务器缓冲
2. 客户端未正确处理 SSE
3. 超时设置太短

**解决方案**：
```nginx
# Nginx 配置
proxy_buffering off;
proxy_cache off;
proxy_set_header Connection '';
chunked_transfer_encoding off;
```

### 问题：连接断开

**可能原因**：
1. 任务执行时间超过超时限制
2. 网络不稳定

**解决方案**：
- 增加客户端超时时间
- 实现重连机制
- 添加心跳检测

## 最佳实践

1. **始终处理错误事件**
   ```python
   if event_type == "error":
       handle_error(event_data["message"])
   ```

2. **显示执行进度**
   ```python
   if event_type == "step":
       progress = step / max_steps * 100
       update_progress_bar(progress)
   ```

3. **区分思考和内容**
   ```python
   if event_type == "thinking":
       show_in_gray(delta)  # 以灰色显示思考过程
   elif event_type == "content":
       show_in_black(delta)  # 正常显示回复内容
   ```

4. **超时处理**
   ```python
   async with httpx.AsyncClient(timeout=httpx.Timeout(
       connect=10.0,    # 连接超时
       read=120.0,      # 读取超时
       write=10.0,      # 写入超时
   )) as client:
       ...
   ```

## 测试工具

项目提供了测试脚本 `test_stream.py`：

```bash
# 运行流式输出测试
uv run python test_stream.py
```

该脚本会：
- 连接流式 API
- 彩色显示不同类型的事件
- 展示完整的执行过程

## 注意事项

1. **并发限制** - 每个连接会占用一个 agent 实例，注意服务器资源
2. **超时设置** - 确保客户端超时时间大于任务预期执行时间
3. **错误处理** - 必须处理网络中断、超时等异常情况
4. **资源清理** - 确保连接正确关闭，释放资源

## 相关文档

- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [Server-Sent Events (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [HTTPX Streaming](https://www.python-httpx.org/quickstart/#streaming-responses)
