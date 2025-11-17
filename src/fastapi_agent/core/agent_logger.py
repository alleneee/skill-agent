"""Agent run logger with structured logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi_agent.schemas.message import Message, ToolCall


class AgentLogger:
    """Agent run logger for recording complete interaction process.

    Features:
    - Records each agent run to separate log file
    - JSON-structured logging for easy parsing
    - Tracks LLM requests/responses, tool calls, and results
    - Logs stored in ~/.fastapi-agent/log/ directory

    Each log file contains a complete trace of an agent run, including:
    - User message
    - LLM requests and responses (with thinking)
    - Tool calls and execution results
    - Token usage and performance metrics
    """

    def __init__(self, log_dir: str | None = None):
        """Initialize logger.

        Args:
            log_dir: Custom log directory (defaults to ~/.fastapi-agent/log/)
        """
        # Use ~/.fastapi-agent/log/ directory for logs
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path.home() / ".fastapi-agent" / "log"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file: Path | None = None
        self.log_index = 0

    def start_new_run(self, run_id: str | None = None) -> Path:
        """Start new run, create new log file.

        Args:
            run_id: Optional custom run ID (defaults to timestamp)

        Returns:
            Path to the created log file
        """
        if run_id:
            log_filename = f"agent_run_{run_id}.log"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"agent_run_{timestamp}.log"

        self.log_file = self.log_dir / log_filename
        self.log_index = 0

        # Write log header
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"FastAPI Agent Run Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Log File: {self.log_file}\n")
            f.write("=" * 80 + "\n\n")

        return self.log_file

    def log_request(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        token_count: int | None = None,
    ):
        """Log LLM request.

        Args:
            messages: Message list
            tools: Tool schema list (optional)
            token_count: Current token count (optional)
        """
        self.log_index += 1

        # Build complete request data structure
        request_data = {
            "messages": [],
            "tools": [],
        }

        if token_count is not None:
            request_data["token_count"] = token_count

        # Convert messages to JSON serializable format
        for msg in messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.thinking:
                msg_dict["thinking"] = msg.thinking
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name

            request_data["messages"].append(msg_dict)

        # Only record tool names
        if tools:
            request_data["tools"] = [tool.get("name", "unknown") for tool in tools]

        # Format as JSON
        content = "LLM Request:\n\n"
        content += json.dumps(request_data, indent=2, ensure_ascii=False)

        self._write_log("REQUEST", content)

    def log_response(
        self,
        content: str,
        thinking: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str | None = None,
    ):
        """Log LLM response.

        Args:
            content: Response content
            thinking: Thinking content (optional)
            tool_calls: Tool call list (optional)
            finish_reason: Finish reason (optional)
        """
        self.log_index += 1

        # Build complete response data structure
        response_data = {
            "content": content,
        }

        if thinking:
            response_data["thinking"] = thinking

        if tool_calls:
            response_data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in tool_calls
            ]

        if finish_reason:
            response_data["finish_reason"] = finish_reason

        # Format as JSON
        log_content = "LLM Response:\n\n"
        log_content += json.dumps(response_data, indent=2, ensure_ascii=False)

        self._write_log("RESPONSE", log_content)

    def log_tool_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        content: str | None = None,
        error: str | None = None,
        execution_time: float | None = None,
    ):
        """Log tool execution result.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            success: Whether successful
            content: Result content (on success)
            error: Error message (on failure)
            execution_time: Execution time in seconds (optional)
        """
        self.log_index += 1

        # Build complete tool execution result data structure
        tool_result_data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
        }

        if execution_time is not None:
            tool_result_data["execution_time_seconds"] = round(execution_time, 3)

        if success:
            # Truncate long content for readability
            if content and len(content) > 2000:
                tool_result_data["result"] = content[:2000] + "\n...(truncated)"
                tool_result_data["result_length"] = len(content)
            else:
                tool_result_data["result"] = content
        else:
            tool_result_data["error"] = error

        # Format as JSON
        log_content = "Tool Execution:\n\n"
        log_content += json.dumps(tool_result_data, indent=2, ensure_ascii=False)

        self._write_log("TOOL_EXECUTION", log_content)

    def log_step(
        self,
        step: int,
        max_steps: int,
        token_count: int | None = None,
        token_limit: int | None = None,
    ):
        """Log agent step information.

        Args:
            step: Current step number
            max_steps: Maximum steps
            token_count: Current token count (optional)
            token_limit: Token limit (optional)
        """
        self.log_index += 1

        step_data = {
            "step": step,
            "max_steps": max_steps,
        }

        if token_count is not None:
            step_data["token_count"] = token_count

        if token_limit is not None:
            step_data["token_limit"] = token_limit
            step_data["token_usage_percent"] = round((token_count / token_limit) * 100, 2)

        content = "Agent Step:\n\n"
        content += json.dumps(step_data, indent=2, ensure_ascii=False)

        self._write_log("STEP", content)

    def log_completion(
        self,
        final_response: str,
        total_steps: int,
        reason: str = "task_completed",
    ):
        """Log agent run completion.

        Args:
            final_response: Final response content
            total_steps: Total steps executed
            reason: Completion reason (task_completed, max_steps_reached, error)
        """
        self.log_index += 1

        completion_data = {
            "final_response": final_response,
            "total_steps": total_steps,
            "reason": reason,
        }

        content = "Run Completion:\n\n"
        content += json.dumps(completion_data, indent=2, ensure_ascii=False)

        self._write_log("COMPLETION", content)

        # Write footer
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n")

    def log_event(self, event_type: str, data: dict[str, Any] | None = None):
        """Log a general event.

        Args:
            event_type: Event type identifier
            data: Event data dictionary (optional)
        """
        self.log_index += 1

        event_data = {
            "event_type": event_type,
        }

        if data:
            event_data.update(data)

        content = f"Event ({event_type}):\n\n"
        content += json.dumps(event_data, indent=2, ensure_ascii=False)

        self._write_log("EVENT", content)

    def _write_log(self, log_type: str, content: str):
        """Write log entry.

        Args:
            log_type: Log type (REQUEST, RESPONSE, TOOL_EXECUTION, STEP, COMPLETION)
            content: Log content
        """
        if self.log_file is None:
            return

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write("\n" + "-" * 80 + "\n")
            f.write(f"[{self.log_index}] {log_type}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
            f.write("-" * 80 + "\n")
            f.write(content + "\n")

    def get_log_file_path(self) -> Path | None:
        """Get current log file path.

        Returns:
            Path to log file, or None if no run has been started
        """
        return self.log_file
