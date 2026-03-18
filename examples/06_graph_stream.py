"""
Graph 流式执行示例

展示如何使用 stream() 方法实时监控图执行过程。

运行方式:
    uv run python examples/06_graph_stream.py
"""

import asyncio
from typing import TypedDict

from omni_agent.core import END, START, StateGraph


class ProcessState(TypedDict):
    data: str
    step_count: int


async def preprocess(state: ProcessState) -> dict:
    """预处理步骤"""
    await asyncio.sleep(0.1)
    return {"data": state["data"].strip(), "step_count": state["step_count"] + 1}


async def transform(state: ProcessState) -> dict:
    """转换步骤"""
    await asyncio.sleep(0.1)
    return {"data": state["data"].upper(), "step_count": state["step_count"] + 1}


async def validate(state: ProcessState) -> dict:
    """验证步骤"""
    await asyncio.sleep(0.1)
    return {"data": f"[VALID] {state['data']}", "step_count": state["step_count"] + 1}


async def main():
    graph = StateGraph(ProcessState)

    graph.add_node("preprocess", preprocess)
    graph.add_node("transform", transform)
    graph.add_node("validate", validate)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "transform")
    graph.add_edge("transform", "validate")
    graph.add_edge("validate", END)

    app = graph.compile()

    initial_state: ProcessState = {
        "data": "  hello world  ",
        "step_count": 0,
    }

    print("=== 流式执行监控 ===\n")

    async for event in app.stream(initial_state):
        event_type = event["type"]

        if event_type == "node_start":
            print(f"[开始] 节点: {event['node']}")
            print(f"        当前数据: {event['state']['data']}")

        elif event_type == "node_end":
            print(f"[完成] 节点: {event['node']}")
            print(f"        更新: {event['update']}")
            print(f"        新状态: {event['state']['data']}")
            print()

        elif event_type == "done":
            print("=== 执行完成 ===")
            print(f"最终数据: {event['state']['data']}")
            print(f"总步骤数: {event['state']['step_count']}")


if __name__ == "__main__":
    asyncio.run(main())
