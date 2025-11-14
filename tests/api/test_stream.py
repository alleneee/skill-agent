#!/usr/bin/env python3
"""测试流式输出功能的脚本"""

import httpx
import json
import asyncio


async def test_stream():
    """测试流式 API"""
    url = "http://localhost:8000/api/v1/agent/run/stream"

    payload = {
        "message": "你好！请简单介绍一下你自己，并告诉我今天是星期几。",
        "max_steps": 3
    }

    print("🚀 开始测试流式输出...")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            print(f"状态码: {response.status_code}\n")

            if response.status_code != 200:
                print(f"错误: {await response.aread()}")
                return

            # 读取 SSE 流
            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                # 解析 SSE 格式
                if line.startswith("data: "):
                    data_str = line[6:]  # 移除 "data: " 前缀

                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type")
                        event_data = event.get("data", {})

                        # 根据事件类型显示不同的输出
                        if event_type == "step":
                            step = event_data.get("step")
                            max_steps = event_data.get("max_steps")
                            tokens = event_data.get("tokens")
                            print(f"\n📍 Step {step}/{max_steps} | Tokens: {tokens}")
                            print("-" * 60)

                        elif event_type == "thinking":
                            delta = event_data.get("delta", "")
                            print(f"💭 思考: {delta}", end="", flush=True)

                        elif event_type == "content":
                            delta = event_data.get("delta", "")
                            print(f"{delta}", end="", flush=True)

                        elif event_type == "tool_call":
                            tool = event_data.get("tool")
                            arguments = event_data.get("arguments", {})
                            print(f"\n🔧 调用工具: {tool}")
                            print(f"   参数: {json.dumps(arguments, ensure_ascii=False, indent=2)}")

                        elif event_type == "tool_result":
                            tool = event_data.get("tool")
                            success = event_data.get("success")
                            execution_time = event_data.get("execution_time", 0)
                            print(f"\n✅ 工具结果: {tool} ({'成功' if success else '失败'})")
                            print(f"   执行时间: {execution_time:.2f}秒")
                            if event_data.get("content"):
                                content = event_data["content"][:200]  # 限制显示长度
                                print(f"   内容: {content}...")

                        elif event_type == "done":
                            message = event_data.get("message", "")
                            steps = event_data.get("steps", 0)
                            print(f"\n\n🎉 完成!")
                            print(f"   总步骤: {steps}")
                            print(f"   最终回复: {message}")

                        elif event_type == "error":
                            error_msg = event_data.get("message", "")
                            print(f"\n\n❌ 错误: {error_msg}")

                        elif event_type == "log_file":
                            log_file = event_data.get("log_file", "")
                            print(f"📝 日志文件: {log_file}")

                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}")
                        print(f"原始数据: {data_str}")

                elif line.startswith("event: done"):
                    print("\n\n✅ 流式传输完成!")
                    break

    print("=" * 60)
    print("测试完成！")


if __name__ == "__main__":
    asyncio.run(test_stream())
