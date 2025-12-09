"""Agent run logger with structured logging and pluggable storage."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi_agent.core.config import settings
from fastapi_agent.core.run_log_storage import RunLogStorage, get_run_log_storage
from fastapi_agent.schemas.message import Message, ToolCall

logger = logging.getLogger(__name__)


class AgentLogger:
    """Agent run logger with async storage backend support.

    Supports both file storage and Redis storage for cloud debugging.
    """

    def __init__(self, storage: Optional[RunLogStorage] = None):
        self._storage = storage
        self.run_id: Optional[str] = None
        self.log_index = 0

    async def _get_storage(self) -> RunLogStorage:
        if self._storage is None:
            self._storage = await get_run_log_storage()
        return self._storage

    def _save_event_sync(self, event: dict) -> None:
        self._log_to_console(event)
        if settings.ENABLE_DEBUG_LOGGING:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._save_event_async(event))
            except RuntimeError:
                asyncio.run(self._save_event_async(event))

    def _log_to_console(self, event: dict) -> None:
        event_type = event.get("type", "UNKNOWN")
        data = event.get("data", {})

        if event_type == "RUN_START":
            logger.info(f"\n{'='*80}")
            logger.info(f"[RUN_START] run_id={data.get('run_id')}")
            logger.info(f"{'='*80}")

        elif event_type == "STEP":
            step = data.get('step', 0)
            max_steps = data.get('max_steps', 0)
            token_count = data.get('token_count', 0)
            token_limit = data.get('token_limit', 0)
            usage_pct = data.get('token_usage_percent', 0)
            logger.info(f"\n[STEP] {step}/{max_steps} | tokens={token_count:,}/{token_limit:,} ({usage_pct:.1f}%)")

        elif event_type == "REQUEST":
            tools = data.get("tools", [])
            messages = data.get("messages", [])
            token_count = data.get("token_count", 0)

            logger.info(f"\n{'-'*80}")
            logger.info(f"[REQUEST] messages={len(messages)} tools={len(tools)} tokens={token_count:,}")
            logger.info(f"[REQUEST] tools: {json.dumps(tools, ensure_ascii=False)}")

            for i, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                if role == "system":
                    preview = content[:800] + "..." if len(content) > 800 else content
                    logger.info(f"[REQUEST] msg[{i}] role=system content={json.dumps(preview, ensure_ascii=False)}")
                elif role == "user":
                    logger.info(f"[REQUEST] msg[{i}] role=user content={json.dumps(content, ensure_ascii=False)}")
                elif role == "assistant":
                    if tool_calls:
                        logger.info(f"[REQUEST] msg[{i}] role=assistant tool_calls={json.dumps(tool_calls, ensure_ascii=False)}")
                    if content:
                        preview = content[:300] + "..." if len(content) > 300 else content
                        logger.info(f"[REQUEST] msg[{i}] role=assistant content={json.dumps(preview, ensure_ascii=False)}")
                elif role == "tool":
                    tool_name = msg.get("name", "unknown")
                    tool_call_id = msg.get("tool_call_id", "")
                    preview = content[:500] + "..." if len(content) > 500 else content
                    logger.info(f"[REQUEST] msg[{i}] role=tool name={tool_name} tool_call_id={tool_call_id}")
                    logger.info(f"[REQUEST] msg[{i}] content={json.dumps(preview, ensure_ascii=False)}")

        elif event_type == "RESPONSE":
            content = data.get("content", "")
            thinking = data.get("thinking", "")
            tool_calls = data.get("tool_calls", [])
            finish_reason = data.get("finish_reason", "")
            input_tokens = data.get("input_tokens", 0)
            output_tokens = data.get("output_tokens", 0)

            logger.info(f"\n{'-'*80}")
            logger.info(f"[RESPONSE] input_tokens={input_tokens:,} output_tokens={output_tokens:,} finish_reason={finish_reason}")

            if thinking:
                preview = thinking[:500] + "..." if len(thinking) > 500 else thinking
                logger.info(f"[RESPONSE] thinking={json.dumps(preview, ensure_ascii=False)}")

            if tool_calls:
                logger.info(f"[RESPONSE] tool_calls={json.dumps(tool_calls, ensure_ascii=False)}")

            if content:
                preview = content[:800] + "..." if len(content) > 800 else content
                logger.info(f"[RESPONSE] content={json.dumps(preview, ensure_ascii=False)}")

        elif event_type == "TOOL_EXECUTION":
            tool_name = data.get("tool_name", "unknown")
            arguments = data.get("arguments", {})
            success = data.get("success", False)
            exec_time = data.get("execution_time_seconds", 0)
            result = data.get("result", "")
            error = data.get("error", "")
            result_len = data.get("result_length", len(result or ""))

            logger.info(f"\n{'-'*80}")
            logger.info(f"[TOOL_EXECUTION] tool={tool_name} success={success} time={exec_time:.3f}s result_length={result_len}")
            logger.info(f"[TOOL_EXECUTION] arguments={json.dumps(arguments, ensure_ascii=False)}")

            if success and result:
                preview = result[:1000] + "..." if len(result) > 1000 else result
                logger.info(f"[TOOL_EXECUTION] result={json.dumps(preview, ensure_ascii=False)}")
            elif error:
                logger.info(f"[TOOL_EXECUTION] error={json.dumps(error, ensure_ascii=False)}")

        elif event_type == "COMPLETION":
            steps = data.get("total_steps", 0)
            reason = data.get("reason", "unknown")
            final_response = data.get("final_response", "")

            logger.info(f"\n{'='*80}")
            logger.info(f"[COMPLETION] total_steps={steps} reason={reason}")
            if final_response:
                preview = final_response[:500] + "..." if len(final_response) > 500 else final_response
                logger.info(f"[COMPLETION] final_response={json.dumps(preview, ensure_ascii=False)}")
            logger.info(f"{'='*80}\n")

    async def _save_event_async(self, event: dict) -> None:
        if not self.run_id:
            return
        storage = await self._get_storage()
        await storage.save_event(self.run_id, event)

    def start_new_run(self, run_id: Optional[str] = None) -> str:
        if run_id:
            self.run_id = run_id
        else:
            self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_index = 0

        self._save_event_sync({
            "type": "RUN_START",
            "index": 0,
            "data": {"run_id": self.run_id}
        })
        return self.run_id

    def log_request(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        token_count: Optional[int] = None,
    ):
        self.log_index += 1
        request_data = {
            "messages": [],
            "tools": [t.get("name", "unknown") for t in (tools or [])],
        }
        if token_count is not None:
            request_data["token_count"] = token_count

        for msg in messages:
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.thinking:
                msg_dict["thinking"] = msg.thinking
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name
            request_data["messages"].append(msg_dict)

        self._save_event_sync({
            "type": "REQUEST",
            "index": self.log_index,
            "data": request_data
        })

    def log_response(
        self,
        content: str,
        thinking: Optional[str] = None,
        tool_calls: Optional[list[ToolCall]] = None,
        finish_reason: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ):
        self.log_index += 1
        response_data = {"content": content}
        if thinking:
            response_data["thinking"] = thinking
        if tool_calls:
            response_data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in tool_calls
            ]
        if finish_reason:
            response_data["finish_reason"] = finish_reason
        if input_tokens is not None:
            response_data["input_tokens"] = input_tokens
        if output_tokens is not None:
            response_data["output_tokens"] = output_tokens

        self._save_event_sync({
            "type": "RESPONSE",
            "index": self.log_index,
            "data": response_data
        })

    def log_tool_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        content: Optional[str] = None,
        error: Optional[str] = None,
        execution_time: Optional[float] = None,
    ):
        self.log_index += 1
        tool_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
        }
        if execution_time is not None:
            tool_data["execution_time_seconds"] = round(execution_time, 3)
        if success:
            if content and len(content) > 2000:
                tool_data["result"] = content[:2000] + "\n...(truncated)"
                tool_data["result_length"] = len(content)
            else:
                tool_data["result"] = content
        else:
            tool_data["error"] = error

        self._save_event_sync({
            "type": "TOOL_EXECUTION",
            "index": self.log_index,
            "data": tool_data
        })

    def log_step(
        self,
        step: int,
        max_steps: int,
        token_count: Optional[int] = None,
        token_limit: Optional[int] = None,
    ):
        self.log_index += 1
        step_data = {"step": step, "max_steps": max_steps}
        if token_count is not None:
            step_data["token_count"] = token_count
        if token_limit is not None:
            step_data["token_limit"] = token_limit
            step_data["token_usage_percent"] = round((token_count / token_limit) * 100, 2)

        self._save_event_sync({
            "type": "STEP",
            "index": self.log_index,
            "data": step_data
        })

    def log_completion(
        self,
        final_response: str,
        total_steps: int,
        reason: str = "task_completed",
    ):
        self.log_index += 1
        self._save_event_sync({
            "type": "COMPLETION",
            "index": self.log_index,
            "data": {
                "final_response": final_response,
                "total_steps": total_steps,
                "reason": reason
            }
        })

    def log_event(self, event_type: str, data: Optional[dict[str, Any]] = None):
        self.log_index += 1
        self._save_event_sync({
            "type": "EVENT",
            "index": self.log_index,
            "data": {"event_type": event_type, **(data or {})}
        })

    def get_run_id(self) -> Optional[str]:
        return self.run_id
