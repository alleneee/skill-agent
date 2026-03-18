"""
Graph 执行引擎基础示例

展示 StateGraph 的基本用法：顺序执行、状态传递。

运行方式:
    uv run python examples/02_graph_basic.py
"""

import asyncio
from typing import TypedDict

from omni_agent.core import END, START, StateGraph


class SimpleState(TypedDict):
    input: str
    step1_result: str
    step2_result: str
    final_result: str


async def step1(state: SimpleState) -> dict:
    """第一步：处理输入"""
    processed = state["input"].upper()
    return {"step1_result": f"Step1 处理: {processed}"}


async def step2(state: SimpleState) -> dict:
    """第二步：继续处理"""
    combined = f"{state['step1_result']} -> Step2 完成"
    return {"step2_result": combined}


async def finalize(state: SimpleState) -> dict:
    """最终步骤：生成结果"""
    final = f"最终结果: {state['step2_result']}"
    return {"final_result": final}


async def main():
    graph = StateGraph(SimpleState)

    graph.add_node("step1", step1)
    graph.add_node("step2", step2)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "step1")
    graph.add_edge("step1", "step2")
    graph.add_edge("step2", "finalize")
    graph.add_edge("finalize", END)

    app = graph.compile()

    initial_state: SimpleState = {
        "input": "hello world",
        "step1_result": "",
        "step2_result": "",
        "final_result": "",
    }

    result = await app.invoke(initial_state)

    print("=== 执行结果 ===")
    print(f"输入: {result['input']}")
    print(f"Step1: {result['step1_result']}")
    print(f"Step2: {result['step2_result']}")
    print(f"最终: {result['final_result']}")

    print("\n=== 图结构 ===")
    structure = app.get_graph_structure()
    print(f"节点: {structure['nodes']}")
    print(f"边数: {len(structure['edges'])}")


if __name__ == "__main__":
    asyncio.run(main())
