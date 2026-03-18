"""Agent 节点 - 将 Agent 包装为图节点。

Enables using existing Agent instances as nodes in StateGraph workflows.
"""

import logging
from collections.abc import Callable
from typing import Any

from omni_agent.core.agent import Agent
from omni_agent.core.llm_client import LLMClient
from omni_agent.tools.base import Tool

logger = logging.getLogger(__name__)


class AgentNode:
    """Wrapper to use Agent as a StateGraph node.

    Example:
        from omni_agent.core import StateGraph, START, END
        from omni_agent.core.agent_node import AgentNode

        class WorkflowState(TypedDict):
            task: str
            result: str
            history: Annotated[list[str], operator.add]

        researcher = AgentNode(
            name="researcher",
            system_prompt="You are a research assistant.",
            llm_client=client,
            tools=[search_tool],
            input_key="task",
            output_key="result",
        )

        graph = StateGraph(WorkflowState)
        graph.add_node("research", researcher)
        graph.add_edge(START, "research")
        graph.add_edge("research", END)
    """

    def __init__(
        self,
        name: str,
        llm_client: LLMClient,
        system_prompt: str = "",
        tools: list[Tool] | None = None,
        input_key: str = "input",
        output_key: str = "output",
        history_key: str | None = None,
        max_steps: int = 10,
        transform_input: Callable[[dict[str, Any]], str] | None = None,
        transform_output: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        """Initialize AgentNode.

        Args:
            name: Node name for identification
            llm_client: LLM client instance
            system_prompt: System prompt for the agents
            tools: List of tools available to the agents
            input_key: State key to read input from
            output_key: State key to write output to
            history_key: Optional state key to append execution history
            max_steps: Maximum execution steps
            transform_input: Custom function to transform state to input message
            transform_output: Custom function to transform agents output to state update
        """
        self.name = name
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.input_key = input_key
        self.output_key = output_key
        self.history_key = history_key
        self.max_steps = max_steps
        self.transform_input = transform_input
        self.transform_output = transform_output

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute agents and return state update.

        Args:
            state: Current workflow state

        Returns:
            State update dictionary
        """
        if self.transform_input:
            input_message = self.transform_input(state)
        else:
            input_message = str(state.get(self.input_key, ""))

        if not input_message:
            logger.warning("AgentNode %s received empty input", self.name)
            return {}

        agent = Agent(
            llm_client=self.llm_client,
            system_prompt=self.system_prompt,
            tools=self.tools,
            max_steps=self.max_steps,
        )

        agent.add_user_message(input_message)
        result_message, _ = await agent.run()

        if self.transform_output:
            return self.transform_output(result_message, state)

        update: dict[str, Any] = {self.output_key: result_message}

        if self.history_key:
            update[self.history_key] = [f"[{self.name}] {result_message}"]

        return update


class ToolNode:
    """Wrapper to use a Tool as a StateGraph node.

    Useful for deterministic operations that don't need LLM reasoning.

    Example:
        save_node = ToolNode(
            tool=write_file_tool,
            input_mapper=lambda s: {"file_path": s["path"], "content": s["content"]},
            output_key="saved",
        )
    """

    def __init__(
        self,
        tool: Tool,
        input_mapper: Callable[[dict[str, Any]], dict[str, Any]],
        output_key: str = "tool_result",
        history_key: str | None = None,
    ) -> None:
        """Initialize ToolNode.

        Args:
            tool: Tool instance to execute
            input_mapper: Function to map state to tool parameters
            output_key: State key to write result to
            history_key: Optional state key to append execution history
        """
        self.tool = tool
        self.input_mapper = input_mapper
        self.output_key = output_key
        self.history_key = history_key

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute tool and return state update."""
        params = self.input_mapper(state)
        result = await self.tool.execute(**params)  # type: ignore[arg-type]

        update: dict[str, Any] = {
            self.output_key: result.content if result.success else result.error
        }

        if self.history_key:
            status = "success" if result.success else "failed"
            update[self.history_key] = [
                f"[{self.tool.name}:{status}] {result.content or result.error}"
            ]

        return update


def create_router(
    condition_key: str,
    route_map: dict[str, str],
    default: str = "__end__",
) -> Callable[[dict[str, Any]], str]:
    """Create a condition function for conditional edges.

    Args:
        condition_key: State key to check
        route_map: Mapping from condition values to target nodes
        default: Default target if condition value not in map

    Returns:
        Condition function for add_conditional_edges

    Example:
        router = create_router(
            "status",
            {"needs_review": "reviewer", "approved": "__end__"},
            default="researcher"
        )
        graph.add_conditional_edges("analyzer", router)
    """

    def condition(state: dict[str, Any]) -> str:
        value = state.get(condition_key)
        return route_map.get(str(value), default)

    return condition
