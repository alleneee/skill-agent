"""沙箱工具包 - 为会话创建所有沙箱工具。"""

from omni_agent.sandbox.manager import SandboxInstance, SandboxManager
from omni_agent.sandbox.tools import (
    SandboxEditTool,
    SandboxJupyterTool,
    SandboxListDirTool,
    SandboxReadTool,
    SandboxShellTool,
    SandboxWriteTool,
)
from omni_agent.tools.base import Tool


class SandboxToolkit:
    """创建沙箱隔离工具的工厂。

    创建在隔离沙箱环境中执行的完整工具集，每个会话一个沙箱。

    用法：
        manager = SandboxManager(base_url="http://localhost:8080")
        await manager.initialize()

        toolkit = SandboxToolkit(manager)
        tools = await toolkit.get_tools("session-123")

        # tools 包含：bash, read_file, write_file, edit_file, python, list_dir
    """

    def __init__(
        self,
        sandbox_manager: SandboxManager,
        enable_shell: bool = True,
        enable_file_ops: bool = True,
        enable_jupyter: bool = True,
    ) -> None:
        self._manager = sandbox_manager
        self._enable_shell = enable_shell
        self._enable_file_ops = enable_file_ops
        self._enable_jupyter = enable_jupyter

    async def get_tools(self, session_id: str) -> list[Tool]:
        """获取会话的所有沙箱工具。

        Args:
            session_id: 会话标识符

        Returns:
            绑定到会话沙箱的 Tool 实例列表
        """
        sandbox = await self._manager.get_sandbox(session_id)
        return self._create_tools(sandbox)

    def _create_tools(self, sandbox: SandboxInstance) -> list[Tool]:
        """为沙箱创建工具实例。"""
        tools: list[Tool] = []

        if self._enable_shell:
            tools.append(SandboxShellTool(sandbox))

        if self._enable_file_ops:
            tools.extend(
                [
                    SandboxReadTool(sandbox),
                    SandboxWriteTool(sandbox),
                    SandboxEditTool(sandbox),
                    SandboxListDirTool(sandbox),
                ]
            )

        if self._enable_jupyter:
            tools.append(SandboxJupyterTool(sandbox))

        return tools

    async def cleanup_session(self, session_id: str) -> bool:
        """移除会话的沙箱。

        Args:
            session_id: 会话标识符

        Returns:
            如果移除成功返回 True，未找到返回 False
        """
        return await self._manager.remove_sandbox(session_id)

    @property
    def manager(self) -> SandboxManager:
        return self._manager
