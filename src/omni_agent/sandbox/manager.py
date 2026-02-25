"""沙箱生命周期管理器 - 每个会话一个沙箱。"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class SandboxInstance:
    """表示会话的沙箱实例。"""

    session_id: str
    sandbox_id: str = field(default_factory=lambda: str(uuid4()))
    base_url: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    _client: Any = field(default=None, repr=False)

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Sandbox client not initialized")
        return self._client

    def touch(self) -> None:
        self.last_accessed = datetime.now()

    @property
    def home_dir(self) -> str:
        if self._client:
            return self._client.sandbox.get_context().home_dir
        return "/home/user"


class SandboxManager:
    """管理每个会话的沙箱实例。

    特性：
    - 每个 session_id 一个沙箱
    - 首次访问时自动创建沙箱
    - 基于 TTL 清理空闲沙箱
    - 使用锁实现异步安全

    用法：
        manager = SandboxManager(base_url="http://localhost:8080")

        # 获取或创建会话的沙箱
        sandbox = await manager.get_sandbox("session-123")

        # 执行命令
        result = sandbox.client.shell.exec_command(command="ls -la")

        # 完成后清理
        await manager.remove_sandbox("session-123")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        auto_start_docker: bool = False,
        docker_image: str = "ghcr.io/agents-infra/sandbox:latest",
        ttl_seconds: int = 3600,
        max_sandboxes: int = 100,
    ) -> None:
        self._base_url = base_url
        self._auto_start_docker = auto_start_docker
        self._docker_image = docker_image
        self._ttl_seconds = ttl_seconds
        self._max_sandboxes = max_sandboxes

        self._sandboxes: dict[str, SandboxInstance] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._docker_container_id: Optional[str] = None

    async def initialize(self) -> None:
        """初始化沙箱管理器。"""
        if self._initialized:
            return

        if self._auto_start_docker:
            await self._start_docker_container()

        self._initialized = True
        logger.info(f"SandboxManager initialized, base_url={self._base_url}")

    async def _start_docker_container(self) -> None:
        """如果未运行则启动沙箱 Docker 容器。"""
        import subprocess

        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"ancestor={self._docker_image}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                self._docker_container_id = result.stdout.strip().split("\n")[0]
                logger.info(f"Using existing sandbox container: {self._docker_container_id}")
                return

            logger.info(f"Starting sandbox container: {self._docker_image}")
            result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--security-opt", "seccomp=unconfined",
                    "-p", "8080:8080",
                    self._docker_image,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self._docker_container_id = result.stdout.strip()
                logger.info(f"Started sandbox container: {self._docker_container_id}")
                await asyncio.sleep(3)
            else:
                logger.error(f"Failed to start container: {result.stderr}")
        except Exception as e:
            logger.error(f"Docker startup failed: {e}")

    async def get_sandbox(self, session_id: str) -> SandboxInstance:
        """获取或创建会话的沙箱。

        Args:
            session_id: 会话标识符

        Returns:
            会话的 SandboxInstance
        """
        async with self._lock:
            if session_id in self._sandboxes:
                sandbox = self._sandboxes[session_id]
                sandbox.touch()
                return sandbox

            if len(self._sandboxes) >= self._max_sandboxes:
                await self._cleanup_oldest()

            sandbox = await self._create_sandbox(session_id)
            self._sandboxes[session_id] = sandbox
            return sandbox

    async def _create_sandbox(self, session_id: str) -> SandboxInstance:
        """创建新的沙箱实例。"""
        try:
            from agent_sandbox import Sandbox
        except ImportError:
            raise RuntimeError(
                "agents-sandbox not installed. Run: uv add agents-sandbox"
            )

        client = Sandbox(base_url=self._base_url)

        sandbox = SandboxInstance(
            session_id=session_id,
            base_url=self._base_url,
            _client=client,
        )

        logger.info(f"Created sandbox for session: {session_id}")
        return sandbox

    async def remove_sandbox(self, session_id: str) -> bool:
        """移除会话的沙箱。

        Args:
            session_id: 会话标识符

        Returns:
            如果移除成功返回 True，未找到返回 False
        """
        async with self._lock:
            if session_id not in self._sandboxes:
                return False

            del self._sandboxes[session_id]
            logger.info(f"Removed sandbox for session: {session_id}")
            return True

    async def _cleanup_oldest(self) -> None:
        """移除最旧的沙箱以腾出空间。"""
        if not self._sandboxes:
            return

        oldest_session = min(
            self._sandboxes.keys(),
            key=lambda k: self._sandboxes[k].last_accessed,
        )
        del self._sandboxes[oldest_session]
        logger.info(f"Cleaned up oldest sandbox: {oldest_session}")

    async def cleanup_expired(self) -> int:
        """移除超过 TTL 的沙箱。

        Returns:
            移除的沙箱数量
        """
        async with self._lock:
            now = datetime.now()
            expired = [
                session_id
                for session_id, sandbox in self._sandboxes.items()
                if (now - sandbox.last_accessed).total_seconds() > self._ttl_seconds
            ]

            for session_id in expired:
                del self._sandboxes[session_id]

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sandboxes")

            return len(expired)

    async def shutdown(self) -> None:
        """关闭管理器并清理资源。"""
        async with self._lock:
            self._sandboxes.clear()

        if self._docker_container_id and self._auto_start_docker:
            import subprocess
            try:
                subprocess.run(
                    ["docker", "stop", self._docker_container_id],
                    capture_output=True,
                )
                logger.info(f"Stopped sandbox container: {self._docker_container_id}")
            except Exception as e:
                logger.error(f"Failed to stop container: {e}")

        self._initialized = False
        logger.info("SandboxManager shutdown complete")

    @property
    def active_sandboxes(self) -> int:
        return len(self._sandboxes)

    def get_stats(self) -> dict[str, Any]:
        return {
            "active_sandboxes": self.active_sandboxes,
            "max_sandboxes": self._max_sandboxes,
            "ttl_seconds": self._ttl_seconds,
            "base_url": self._base_url,
        }
