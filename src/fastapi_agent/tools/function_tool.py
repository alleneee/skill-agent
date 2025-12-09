"""Function tool - dynamically create tools from callable functions."""

import inspect
from typing import Any, Callable, get_type_hints, Optional

from fastapi_agent.tools.base import Tool, ToolResult


def _extract_docstring(func: Callable) -> str:
    """Extract description from function docstring."""
    doc = inspect.getdoc(func)
    if not doc:
        return func.__name__
    # Return first line as description
    return doc.split('\n')[0].strip()


def _generate_json_schema(func: Callable) -> dict[str, Any]:
    """Generate JSON Schema from function signature.

    Simple implementation that handles basic types.
    """
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip self, cls, and return annotations
        if param_name in ('self', 'cls', 'return'):
            continue

        param_type = type_hints.get(param_name, str)
        param_schema = _type_to_json_schema(param_type)

        # Try to extract description from docstring
        param_description = f"Parameter: {param_name}"

        properties[param_name] = {
            **param_schema,
            "description": param_description
        }

        # Required if no default value
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


def _type_to_json_schema(python_type: type) -> dict[str, Any]:
    """Convert Python type to JSON Schema type."""
    # Handle Optional types
    origin = getattr(python_type, '__origin__', None)
    if origin is type(None) or str(python_type).startswith('typing.Optional'):
        # Extract inner type from Optional[T]
        args = getattr(python_type, '__args__', ())
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
        args = getattr(python_type, '__args__', ())
        if args:
            return {
                "type": "array",
                "items": _type_to_json_schema(args[0])
            }
        return {"type": "array"}

    # Default to string
    return {"type": "string"}


class FunctionTool(Tool):
    """A tool created from a callable function.

    This allows creating tools dynamically without subclassing Tool.
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
    ):
        """Initialize FunctionTool.

        Args:
            func: The callable function to wrap
            name: Tool name (defaults to function name)
            description: Tool description (defaults to first line of docstring)
            parameters: JSON Schema for parameters (auto-generated if not provided)
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
        """Execute the wrapped function."""
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
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
) -> Tool:
    """Create a Tool from a callable function.

    Args:
        func: Callable function to wrap
        name: Optional tool name (defaults to function name)
        description: Optional description (defaults to docstring)
        parameters: Optional JSON Schema (auto-generated if not provided)

    Returns:
        Tool instance

    Example:
        >>> def my_tool(query: str) -> str:
        ...     '''Search for information'''
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
