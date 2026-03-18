"""图执行引擎，受 LangGraph 启发。

提供声明式方式定义 Agent 工作流：
- 节点 (Nodes): 处理状态的函数
- 边 (Edges): 节点之间的连接（顺序、条件、并行）
- 状态 (State): TypedDict，支持可选的 reducer 用于并行执行时的状态合并

核心概念:
    - START: 图的入口点，不是真实节点
    - END: 图的终止点，表示执行结束
    - StateGraph: 图构建器，用于定义节点和边
    - CompiledGraph: 编译后的可执行图

使用示例:
    from omni_agent.core.graph import StateGraph, START, END
    from typing import TypedDict, Annotated
    import operator

    class MyState(TypedDict):
        messages: Annotated[list[str], operator.add]  # 使用 operator.add 作为 reducer
        result: str

    def node_a(state: MyState) -> dict:
        return {"messages": ["A executed"]}

    def node_b(state: MyState) -> dict:
        return {"messages": ["B executed"], "result": "done"}

    graph = StateGraph(MyState)
    graph.add_node("a", node_a)
    graph.add_node("b", node_b)
    graph.add_edge(START, "a")
    graph.add_edge("a", "b")
    graph.add_edge("b", END)

    app = graph.compile()
    result = await app.invoke({"messages": [], "result": ""})
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Generic,
    TypeVar,
    get_origin,
    get_type_hints,
)

logger = logging.getLogger(__name__)

# 特殊节点标识符
START = "__start__"  # 图的入口点
END = "__end__"  # 图的终止点

# 类型定义
StateType = TypeVar("StateType", bound=dict[str, Any])
NodeFunc = Callable[[Any], dict[str, Any] | Coroutine[Any, Any, dict[str, Any]]]
ConditionFunc = Callable[[Any], str]


class EdgeType(Enum):
    """边类型枚举."""

    NORMAL = "normal"  # 普通边：无条件连接
    CONDITIONAL = "conditional"  # 条件边：根据条件函数决定目标


@dataclass
class Edge:
    """图中的边，连接两个节点."""

    source: str  # 源节点名称
    target: str  # 目标节点名称
    edge_type: EdgeType = EdgeType.NORMAL
    condition: ConditionFunc | None = None  # 条件函数（仅条件边使用）
    condition_map: dict[str, str] | None = None  # 条件结果到节点名的映射


@dataclass
class Node:
    """图中的节点，包含处理函数."""

    name: str  # 节点名称
    func: NodeFunc  # 节点处理函数，接收状态返回更新
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据


def get_reducer(state_type: type, key: str) -> Callable[[Any, Any], Any] | None:
    """从 Annotated 类型提示中提取 reducer 函数.

    Reducer 用于在并行执行时合并多个节点对同一字段的更新。
    例如 Annotated[list[str], operator.add] 会使用 operator.add 合并列表。

    Args:
        state_type: 状态类型（TypedDict 子类）
        key: 字段名

    Returns:
        reducer 函数，若未定义则返回 None
    """
    try:
        hints = get_type_hints(state_type, include_extras=True)
        hint = hints.get(key)
        if hint is None:
            return None

        origin = get_origin(hint)
        if origin is not None and hasattr(hint, "__metadata__"):
            for meta in hint.__metadata__:
                if callable(meta):
                    return meta
        return None
    except Exception:
        return None


def merge_state(
    current: dict[str, Any],
    update: dict[str, Any],
    state_type: type,
) -> dict[str, Any]:
    """合并状态更新到当前状态.

    对于定义了 reducer 的字段，使用 reducer 函数合并；
    否则直接覆盖原值。

    Args:
        current: 当前状态
        update: 状态更新
        state_type: 状态类型

    Returns:
        合并后的新状态
    """
    result = current.copy()
    for key, value in update.items():
        reducer = get_reducer(state_type, key)
        if reducer is not None and key in result:
            result[key] = reducer(result[key], value)
        else:
            result[key] = value
    return result


class CompiledGraph(Generic[StateType]):
    """编译后的图，可直接执行.

    CompiledGraph 是 StateGraph.compile() 的产物，提供：
    - invoke(): 同步执行整个图
    - stream(): 流式执行，逐步返回节点执行结果
    - get_graph_structure(): 获取图结构用于可视化
    """

    def __init__(
        self,
        nodes: dict[str, Node],
        edges: list[Edge],
        state_type: type,
        entry_point: str,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._state_type = state_type
        self._entry_point = entry_point
        self._adjacency: dict[str, list[Edge]] = {}
        self._build_adjacency()

    def _build_adjacency(self) -> None:
        """构建邻接表，加速边查询."""
        for edge in self._edges:
            if edge.source not in self._adjacency:
                self._adjacency[edge.source] = []
            self._adjacency[edge.source].append(edge)

    def _get_next_nodes(self, current: str, state: dict[str, Any]) -> list[str]:
        """根据边和条件确定下一个要执行的节点.

        对于普通边，直接返回目标节点；
        对于条件边，调用条件函数确定目标。
        """
        edges = self._adjacency.get(current, [])
        next_nodes = []

        for edge in edges:
            if edge.edge_type == EdgeType.NORMAL:
                next_nodes.append(edge.target)
            elif edge.edge_type == EdgeType.CONDITIONAL and edge.condition:
                result = edge.condition(state)
                target = edge.condition_map.get(result, result) if edge.condition_map else result
                if target != END:
                    next_nodes.append(target)
                elif target == END:
                    next_nodes.append(END)

        return next_nodes

    async def _execute_node(self, node_name: str, state: dict[str, Any]) -> dict[str, Any]:
        """执行单个节点并返回状态更新."""
        if node_name == END:
            return {}

        node = self._nodes.get(node_name)
        if node is None:
            raise ValueError(f"Node '{node_name}' not found")

        logger.debug("Executing node: %s", node_name)

        result = node.func(state)
        if asyncio.iscoroutine(result):
            result = await result

        return result if result else {}

    def _get_start_nodes(self) -> list[str]:
        """获取从 START 连接的所有起始节点."""
        start_edges = self._adjacency.get(START, [])
        return [e.target for e in start_edges if e.edge_type == EdgeType.NORMAL]

    async def invoke(
        self,
        initial_state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行图并返回最终状态.

        执行流程:
        1. 从 START 连接的节点开始
        2. 执行当前层的所有节点（支持并行）
        3. 根据边确定下一层节点
        4. 重复直到到达 END 或达到最大迭代次数

        Args:
            initial_state: 初始状态字典
            config: 可选配置，支持 max_iterations（默认 100）

        Returns:
            图执行完成后的最终状态
        """
        state = dict(initial_state)
        start_nodes = self._get_start_nodes()
        current_nodes = start_nodes if start_nodes else [self._entry_point]
        visited: set[str] = set()
        max_iterations = config.get("max_iterations", 100) if config else 100
        iteration = 0

        while current_nodes and iteration < max_iterations:
            iteration += 1

            # 过滤出可执行的节点（非 END 且未访问过）
            executable = [n for n in current_nodes if n != END and n not in visited]

            if not executable:
                if END in current_nodes:
                    break
                break

            # 单节点顺序执行，多节点并行执行
            if len(executable) == 1:
                node_name = executable[0]
                update = await self._execute_node(node_name, state)
                state = merge_state(state, update, self._state_type)
                visited.add(node_name)
                current_nodes = self._get_next_nodes(node_name, state)
            else:
                # 并行执行多个节点
                tasks = [self._execute_node(n, state) for n in executable]
                updates = await asyncio.gather(*tasks)

                for update in updates:
                    state = merge_state(state, update, self._state_type)

                visited.update(executable)

                # 收集所有后继节点
                next_set: set[str] = set()
                for node_name in executable:
                    next_set.update(self._get_next_nodes(node_name, state))
                current_nodes = list(next_set)

        if iteration >= max_iterations:
            logger.warning("Graph execution reached max iterations: %d", max_iterations)

        return state

    async def stream(
        self,
        initial_state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ):
        """流式执行图，逐步产出节点执行事件.

        事件类型:
        - node_start: 节点开始执行
        - node_end: 节点执行完成，包含状态更新
        - done: 图执行完成

        Args:
            initial_state: 初始状态
            config: 可选配置

        Yields:
            包含执行事件的字典
        """
        state = dict(initial_state)
        start_nodes = self._get_start_nodes()
        current_nodes = start_nodes if start_nodes else [self._entry_point]
        visited: set[str] = set()
        max_iterations = config.get("max_iterations", 100) if config else 100
        iteration = 0

        while current_nodes and iteration < max_iterations:
            iteration += 1

            executable = [n for n in current_nodes if n != END and n not in visited]

            if not executable:
                break

            for node_name in executable:
                yield {"type": "node_start", "node": node_name, "state": dict(state)}

                update = await self._execute_node(node_name, state)
                state = merge_state(state, update, self._state_type)
                visited.add(node_name)

                yield {
                    "type": "node_end",
                    "node": node_name,
                    "update": update,
                    "state": dict(state),
                }

            next_set: set[str] = set()
            for node_name in executable:
                next_set.update(self._get_next_nodes(node_name, state))
            current_nodes = list(next_set)

        yield {"type": "done", "state": dict(state)}

    def get_graph_structure(self) -> dict[str, Any]:
        """获取图结构用于可视化."""
        return {
            "nodes": list(self._nodes.keys()),
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                }
                for e in self._edges
            ],
            "entry_point": self._entry_point,
        }


class StateGraph(Generic[StateType]):
    """图构建器，用于定义 Agent 工作流.

    使用链式调用定义节点和边，最后调用 compile() 生成可执行图。

    示例:
        graph = StateGraph(MyState)
        graph.add_node("process", process_func)
        graph.add_edge(START, "process")
        graph.add_edge("process", END)
        app = graph.compile()
    """

    def __init__(self, state_type: type) -> None:
        """初始化 StateGraph.

        Args:
            state_type: 定义状态模式的 TypedDict 类
        """
        self._state_type = state_type
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._entry_point: str | None = None

    def add_node(
        self,
        name: str | NodeFunc,
        func: NodeFunc | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "StateGraph[StateType]":
        """添加节点到图.

        Args:
            name: 节点名称或函数（若为函数，名称从函数名推断）
            func: 节点处理函数（若 name 为函数则可选）
            metadata: 可选的节点元数据

        Returns:
            self，支持链式调用
        """
        node_name: str
        node_func: NodeFunc

        if callable(name) and func is None:
            node_func = name
            node_name = name.__name__
        elif isinstance(name, str) and func is not None:
            node_name = name
            node_func = func
        else:
            raise ValueError("Node function is required")

        if node_name in self._nodes:
            raise ValueError(f"Node '{node_name}' already exists")

        self._nodes[node_name] = Node(
            name=node_name,
            func=node_func,
            metadata=metadata or {},
        )

        return self

    def add_edge(
        self,
        source: str,
        target: str,
    ) -> "StateGraph[StateType]":
        """添加普通边（无条件连接）.

        Args:
            source: 源节点名称（或 START）
            target: 目标节点名称（或 END）

        Returns:
            self，支持链式调用
        """
        if source == START:
            self._entry_point = target

        self._edges.append(
            Edge(
                source=source,
                target=target,
                edge_type=EdgeType.NORMAL,
            )
        )

        return self

    def add_conditional_edges(
        self,
        source: str,
        condition: ConditionFunc,
        path_map: dict[str, str] | list[str] | None = None,
    ) -> "StateGraph[StateType]":
        """添加条件边.

        根据条件函数的返回值动态决定下一个节点。

        Args:
            source: 源节点名称
            condition: 条件函数，接收状态返回目标节点名
            path_map: 可选的条件结果到节点名的映射，或可能目标节点的列表

        Returns:
            self，支持链式调用

        示例:
            def route(state):
                return "yes" if state["should_continue"] else "no"

            graph.add_conditional_edges(
                "decide",
                route,
                {"yes": "continue_node", "no": END}
            )
        """
        condition_map = None
        if isinstance(path_map, list):
            condition_map = {name: name for name in path_map}
        elif isinstance(path_map, dict):
            condition_map = path_map

        self._edges.append(
            Edge(
                source=source,
                target="",
                edge_type=EdgeType.CONDITIONAL,
                condition=condition,
                condition_map=condition_map,
            )
        )

        return self

    def set_entry_point(self, node_name: str) -> "StateGraph[StateType]":
        """设置图的入口点.

        Args:
            node_name: 入口节点名称

        Returns:
            self，支持链式调用
        """
        self._entry_point = node_name
        return self

    def compile(self) -> CompiledGraph[StateType]:
        """编译图为可执行形式.

        验证图的有效性并生成 CompiledGraph。

        Returns:
            可执行的 CompiledGraph

        Raises:
            ValueError: 图无效（无入口点、节点缺失等）
        """
        if self._entry_point is None:
            for edge in self._edges:
                if edge.source == START:
                    self._entry_point = edge.target
                    break

        if self._entry_point is None:
            raise ValueError(
                "No entry point defined. Use add_edge(START, 'node') or set_entry_point()"
            )

        if self._entry_point not in self._nodes and self._entry_point != END:
            raise ValueError(f"Entry point '{self._entry_point}' is not a valid node")

        for edge in self._edges:
            if edge.edge_type == EdgeType.NORMAL:
                if edge.source != START and edge.source not in self._nodes:
                    raise ValueError(f"Edge source '{edge.source}' is not a valid node")
                if edge.target != END and edge.target not in self._nodes:
                    raise ValueError(f"Edge target '{edge.target}' is not a valid node")

        return CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            state_type=self._state_type,
            entry_point=self._entry_point,
        )

    def get_nodes(self) -> list[str]:
        """获取所有节点名称列表."""
        return list(self._nodes.keys())

    def get_edges(self) -> list[tuple[str, str]]:
        """获取边列表，以 (源, 目标) 元组形式返回."""
        return [(e.source, e.target) for e in self._edges if e.edge_type == EdgeType.NORMAL]


class GraphBuilder(StateGraph[StateType]):
    """StateGraph 的别名，用于兼容性."""

    pass
