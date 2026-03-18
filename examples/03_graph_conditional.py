"""
Graph 条件路由示例

展示如何使用条件边实现动态路由。

运行方式:
    uv run python examples/03_graph_conditional.py
"""

import asyncio
from typing import TypedDict

from omni_agent.core import END, START, StateGraph, create_router


class TaskState(TypedDict):
    task: str
    priority: str
    result: str


async def analyzer(state: TaskState) -> dict:
    """分析任务优先级"""
    task = state["task"].lower()
    if "紧急" in task or "urgent" in task:
        return {"priority": "high"}
    elif "重要" in task or "important" in task:
        return {"priority": "medium"}
    return {"priority": "low"}


async def high_priority_handler(state: TaskState) -> dict:
    """处理高优先级任务"""
    return {"result": f"[高优先级] 立即处理: {state['task']}"}


async def medium_priority_handler(state: TaskState) -> dict:
    """处理中优先级任务"""
    return {"result": f"[中优先级] 排队处理: {state['task']}"}


async def low_priority_handler(state: TaskState) -> dict:
    """处理低优先级任务"""
    return {"result": f"[低优先级] 稍后处理: {state['task']}"}


async def main():
    graph = StateGraph(TaskState)

    graph.add_node("analyzer", analyzer)
    graph.add_node("high", high_priority_handler)
    graph.add_node("medium", medium_priority_handler)
    graph.add_node("low", low_priority_handler)

    graph.add_edge(START, "analyzer")

    router = create_router(
        condition_key="priority",
        route_map={
            "high": "high",
            "medium": "medium",
            "low": "low",
        },
        default="low",
    )
    graph.add_conditional_edges("analyzer", router)

    graph.add_edge("high", END)
    graph.add_edge("medium", END)
    graph.add_edge("low", END)

    app = graph.compile()

    test_tasks = [
        "紧急修复生产环境 bug",
        "重要功能需求评审",
        "优化代码风格",
    ]

    print("=== 条件路由测试 ===\n")
    for task in test_tasks:
        result = await app.invoke({"task": task, "priority": "", "result": ""})
        print(f"任务: {task}")
        print(f"优先级: {result['priority']}")
        print(f"结果: {result['result']}\n")


if __name__ == "__main__":
    asyncio.run(main())
