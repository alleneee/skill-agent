"""
Graph 并行执行示例

展示如何使用 StateGraph 实现并行执行和结果聚合。
使用 Annotated 类型和 operator.add 作为 Reducer 合并并行结果。

运行方式:
    uv run python examples/04_graph_parallel.py
"""

import asyncio
import operator
import time
from typing import Annotated, TypedDict

from omni_agent.core import END, START, StateGraph


class ParallelState(TypedDict):
    query: str
    results: Annotated[list[str], operator.add]
    summary: str


async def search_web(state: ParallelState) -> dict:
    """模拟 Web 搜索"""
    await asyncio.sleep(0.2)
    return {"results": [f"[Web] 关于 '{state['query']}' 的搜索结果"]}


async def search_docs(state: ParallelState) -> dict:
    """模拟文档搜索"""
    await asyncio.sleep(0.2)
    return {"results": [f"[Docs] 关于 '{state['query']}' 的文档"]}


async def search_code(state: ParallelState) -> dict:
    """模拟代码搜索"""
    await asyncio.sleep(0.2)
    return {"results": [f"[Code] 关于 '{state['query']}' 的代码示例"]}


async def aggregate(state: ParallelState) -> dict:
    """聚合所有搜索结果"""
    all_results = "\n".join(f"  - {r}" for r in state["results"])
    summary = f"找到 {len(state['results'])} 个结果:\n{all_results}"
    return {"summary": summary}


async def main():
    graph = StateGraph(ParallelState)

    graph.add_node("search_web", search_web)
    graph.add_node("search_docs", search_docs)
    graph.add_node("search_code", search_code)
    graph.add_node("aggregate", aggregate)

    graph.add_edge(START, "search_web")
    graph.add_edge(START, "search_docs")
    graph.add_edge(START, "search_code")

    graph.add_edge("search_web", "aggregate")
    graph.add_edge("search_docs", "aggregate")
    graph.add_edge("search_code", "aggregate")

    graph.add_edge("aggregate", END)

    app = graph.compile()

    initial_state: ParallelState = {
        "query": "Python asyncio",
        "results": [],
        "summary": "",
    }

    start_time = time.time()
    result = await app.invoke(initial_state)
    elapsed = time.time() - start_time

    print("=== 并行执行结果 ===\n")
    print(f"查询: {result['query']}")
    print(f"\n{result['summary']}")
    print(f"\n执行时间: {elapsed:.2f}s (并行执行，3个0.2s任务只需约0.2s)")


if __name__ == "__main__":
    asyncio.run(main())
