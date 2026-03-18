"""函数工具 - 从可调用函数动态创建工具。"""

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from omni_agent.tools.base import Tool, ToolResult


def _extract_docstring(func: Callable) -> str:
    """从函数文档字符串中提取描述。"""
    doc = inspect.getdoc(func)
    if not doc:
        return func.__name__
    # Return first line as description
    return doc.split("\n")[0].strip()


def _generate_json_schema(func: Callable) -> dict[str, Any]:
    """从函数签名生成 JSON Schema。

    处理基本类型的简单实现。
    """
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip self, cls, and return annotations
        if param_name in ("self", "cls", "return"):
            continue

        param_type = type_hints.get(param_name, str)
        param_schema = _type_to_json_schema(param_type)

        # Try to extract description from docstring
        param_description = f"Parameter: {param_name}"

        properties[param_name] = {**param_schema, "description": param_description}

        # Required if no default value
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


def _type_to_json_schema(python_type: type) -> dict[str, Any]:
    """将 Python 类型转换为 JSON Schema 类型。"""
    # Handle Optional types
    origin = getattr(python_type, "__origin__", None)
    if origin is type(None) or str(python_type).startswith("typing.Optional"):
        # Extract inner type from Optional[T]
        args = getattr(python_type, "__args__", ())
        if args:
            return _type_to_json_schema(args[0])

    # Basic type mapping
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }

    # Check for exact match
    if python_type in type_map:
        return type_map[python_type]

    # Check for List[T]
    if origin is list:
        args = getattr(python_type, "__args__", ())
        if args:
            return {"type": "array", "items": _type_to_json_schema(args[0])}
        return {"type": "array"}

    # Default to string
    return {"type": "string"}


class FunctionTool(Tool):
    """从可调用函数创建的工具。

    允许动态创建工具而无需继承 Tool 类。
    """

    def __init__(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
    ):
        """初始化 FunctionTool。

        Args:
            func: 要包装的可调用函数
            name: 工具名称（默认为函数名）
            description: 工具描述（默认为文档字符串的第一行）
            parameters: 参数的 JSON Schema（未提供时自动生成）
        """
        self._func = func
        self._name = name or func.__name__
        self._description = description or _extract_docstring(func)
        self._parameters = parameters or _generate_json_schema(func)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        """执行包装的函数。"""
        try:
            # Check if function is async
            if inspect.iscoroutinefunction(self._func):
                result = await self._func(**kwargs)
            else:
                result = self._func(**kwargs)

            # Handle different return types
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, str):
                return ToolResult(success=True, content=result)
            elif isinstance(result, dict):
                return ToolResult(success=True, content=str(result))
            else:
                return ToolResult(success=True, content=str(result))

        except Exception as e:
            return ToolResult(success=False, error=str(e))


def create_tool_from_function(
    func: Callable,
    name: str | None = None,
    description: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> Tool:
    """从可调用函数创建 Tool。

    Args:
        func: 要包装的可调用函数
        name: 可选的工具名称（默认为函数名）
        description: 可选的描述（默认为文档字符串）
        parameters: 可选的 JSON Schema（未提供时自动生成）

    Returns:
        Tool 实例

    Example:
        >>> def my_tool(query: str) -> str:
        ...     '''搜索信息'''
        ...     return f"Results for: {query}"
        >>> tool = create_tool_from_function(my_tool)
        >>> result = await tool.execute(query="test")
    """
    return FunctionTool(
        func=func,
        name=name,
        description=description,
        parameters=parameters,
    )
