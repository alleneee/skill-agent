"""Bash 命令执行工具。"""

import asyncio
import re
import subprocess
from typing import Any

from .base import Tool, ToolResult

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-[^\s]*r[^\s]*f", re.IGNORECASE),
    re.compile(r"\brm\s+-[^\s]*f[^\s]*r", re.IGNORECASE),
    re.compile(r"\brm\s+--no-preserve-root", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+.*of=/dev/", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;", re.IGNORECASE),
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh|zsh)\b"),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh|zsh)\b"),
    re.compile(r"\bchmod\s+777\s+/", re.IGNORECASE),
    re.compile(r"\bln\s+.*-[^\s]*s[^\s]*\s+/(?:etc|proc|sys|dev|var|boot|root)\b"),
    re.compile(r"\bln\s+--symbolic\s+/(?:etc|proc|sys|dev|var|boot|root)\b"),
]

WRITE_OUTSIDE_WORKSPACE_PATTERNS = [
    re.compile(r">\s*/(?:tmp|etc|var|home|root|usr|opt|boot)/"),
    re.compile(r"\btee\s+/(?:tmp|etc|var|home|root|usr|opt|boot)/"),
    re.compile(r"\bcp\b.*\s+/(?:tmp|etc|var|home|root|usr|opt|boot)/"),
    re.compile(r"\bmv\b.*\s+/(?:tmp|etc|var|home|root|usr|opt|boot)/"),
    re.compile(r"\binstall\b.*\s+/(?:tmp|etc|var|home|root|usr|opt|boot)/"),
]


def _is_dangerous_command(command: str, workspace_dir: str | None = None) -> str | None:
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return "Blocked: dangerous command pattern detected"
    if workspace_dir:
        for pattern in WRITE_OUTSIDE_WORKSPACE_PATTERNS:
            if pattern.search(command):
                return "Blocked: writing to paths outside workspace is not allowed"
    return None


class BashTool(Tool):
    """执行 bash 命令。"""

    def __init__(self, workspace_dir: str | None = None):
        self._workspace_dir = workspace_dir

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute bash commands in the shell. Use for system operations, "
            "file management, running scripts, etc. Returns stdout and stderr."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        }

    @property
    def instructions(self) -> str:
        """Bash 工具使用说明。"""
        return """
<bash_tool_usage>
When using the bash tool:
- Always use absolute paths when possible to avoid path resolution issues
- Check command output carefully before proceeding with subsequent actions
- For critical operations, verify the result with additional commands
- Use timeout parameter for potentially long-running commands
- Remember that commands run in a non-interactive shell environment
</bash_tool_usage>
"""

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        """执行 bash 命令。"""
        try:
            blocked = _is_dangerous_command(command, self._workspace_dir)
            if blocked:
                return ToolResult(success=False, content="", error=blocked)

            cwd = self._workspace_dir or None

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command timed out after {timeout} seconds",
                )

            stdout_text = stdout.decode("utf-8") if stdout else ""
            stderr_text = stderr.decode("utf-8") if stderr else ""

            output = ""
            if stdout_text:
                output += stdout_text
            if stderr_text:
                if output:
                    output += "\n"
                output += f"STDERR:\n{stderr_text}"

            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    content=output,
                    error=f"Command failed with exit code {process.returncode}",
                )

            return ToolResult(success=True, content=output or "Command executed successfully")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
