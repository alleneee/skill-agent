"""基于沙箱的工具，用于隔离执行。"""

from typing import Any

from omni_agent.sandbox.manager import SandboxInstance
from omni_agent.tools.base import Tool, ToolResult


class SandboxShellTool(Tool):
    """在沙箱环境中执行 shell 命令。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute bash commands in isolated sandbox environment. "
            "Safe for running untrusted code. Returns stdout and stderr."
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

    async def execute(self, command: str, timeout: int = 30, **kwargs) -> ToolResult:
        try:
            result = self._sandbox.client.shell.exec_command(
                command=command,
                timeout=timeout,
            )
            output = result.data.output if hasattr(result.data, "output") else str(result.data)
            return ToolResult(success=True, content=output or "Command executed successfully")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SandboxReadTool(Tool):
    """从沙箱文件系统读取文件。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read file content from sandbox filesystem."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, file_path: str, **kwargs) -> ToolResult:
        try:
            result = self._sandbox.client.file.read_file(file=file_path)
            content = result.data.content if hasattr(result.data, "content") else str(result.data)
            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SandboxWriteTool(Tool):
    """向沙箱文件系统写入文件。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file in sandbox filesystem."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str, **kwargs) -> ToolResult:
        try:
            self._sandbox.client.file.write_file(file=file_path, content=content)
            return ToolResult(success=True, content=f"Successfully wrote to {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SandboxEditTool(Tool):
    """使用字符串替换在沙箱中编辑文件。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing a specific string with new content."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        **kwargs,
    ) -> ToolResult:
        try:
            result = self._sandbox.client.file.read_file(file=file_path)
            content = result.data.content if hasattr(result.data, "content") else str(result.data)

            if old_string not in content:
                return ToolResult(
                    success=False,
                    error=f"String not found in {file_path}",
                )

            new_content = content.replace(old_string, new_string, 1)
            self._sandbox.client.file.write_file(file=file_path, content=new_content)

            return ToolResult(success=True, content=f"Successfully edited {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SandboxJupyterTool(Tool):
    """在沙箱内的 Jupyter 内核中执行 Python 代码。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in an isolated Jupyter kernel. "
            "State persists across calls within the same session."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
            },
            "required": ["code"],
        }

    async def execute(self, code: str, **kwargs) -> ToolResult:
        try:
            result = self._sandbox.client.jupyter.execute_code(code=code)
            output = result.data.output if hasattr(result.data, "output") else str(result.data)
            return ToolResult(success=True, content=output or "Code executed successfully")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SandboxListDirTool(Tool):
    """列出沙箱中的目录内容。"""

    def __init__(self, sandbox: SandboxInstance) -> None:
        self._sandbox = sandbox

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List files and directories in sandbox filesystem."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: current directory)",
                },
            },
            "required": [],
        }

    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        try:
            result = self._sandbox.client.shell.exec_command(command=f"ls -la {path}")
            output = result.data.output if hasattr(result.data, "output") else str(result.data)
            return ToolResult(success=True, content=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
