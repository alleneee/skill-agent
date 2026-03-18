"""Omni Agent 的数据模式。"""

from .message import FunctionCall, LLMResponse, Message, ToolCall

__all__ = ["Message", "LLMResponse", "ToolCall", "FunctionCall"]
