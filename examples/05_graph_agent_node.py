"""
AgentNode 示例

展示如何将 Agent 封装为 Graph 节点，实现多 Agent 工作流。

运行方式:
    uv run python examples/05_graph_agent_node.py

注意: 此示例需要设置 LLM_API_KEY 环境变量
"""

import asyncio
import operator
import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv

load_dotenv()

from omni_agent.core import END, START, AgentNode, LLMClient, StateGraph
from omni_agent.tools.file_tools import ReadTool, WriteTool


class ResearchState(TypedDict):
    topic: str
    research_result: str
    article: str
    history: Annotated[list[str], operator.add]


async def main():
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        print("请设置 LLM_API_KEY 环境变量")
        print("此示例需要真实的 LLM API 调用")
        return

    llm_client = LLMClient(
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "anthropic/claude-3-5-sonnet-20241022"),
    )

    researcher = AgentNode(
        name="researcher",
        llm_client=llm_client,
        system_prompt="你是一个研究助手。根据给定的主题进行简要研究，提供3-5个关键点。回复要简洁。",
        tools=[ReadTool()],
        input_key="topic",
        output_key="research_result",
        history_key="history",
        max_steps=3,
    )

    writer = AgentNode(
        name="writer",
        llm_client=llm_client,
        system_prompt="你是一个技术写手。根据研究结果撰写一段简短的介绍文字（100字以内）。",
        tools=[WriteTool()],
        input_key="research_result",
        output_key="article",
        history_key="history",
        max_steps=3,
    )

    graph = StateGraph(ResearchState)

    graph.add_node("researcher", researcher)
    graph.add_node("writer", writer)

    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", END)

    app = graph.compile()

    initial_state: ResearchState = {
        "topic": "Python 异步编程的优势",
        "research_result": "",
        "article": "",
        "history": [],
    }

    print("=== AgentNode 工作流 ===\n")
    print(f"主题: {initial_state['topic']}\n")
    print("正在执行... (这需要 LLM API 调用)\n")

    result = await app.invoke(initial_state)

    print("=== 执行结果 ===\n")
    print(f"研究结果:\n{result['research_result']}\n")
    print(f"文章:\n{result['article']}\n")
    print(f"执行历史: {result['history']}")


if __name__ == "__main__":
    asyncio.run(main())
