from dataclasses import dataclass, field
from enum import Enum


class AcpBackendId(str, Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    QWEN = "qwen"
    CODEX = "codex"
    GOOSE = "goose"
    AUGGIE = "auggie"
    KIMI = "kimi"
    OPENCODE = "opencode"
    IFLOW = "iflow"
    CUSTOM = "custom"


@dataclass
class AcpBackendConfig:
    id: str
    name: str
    cli_command: str | None = None
    default_cli_path: str | None = None
    acp_args: list[str] = field(default_factory=lambda: ["--experimental-acp"])
    auth_required: bool = False
    enabled: bool = True
    supports_streaming: bool = False
    env: dict[str, str] = field(default_factory=dict)


DEFAULT_ACP_ARGS = ["--experimental-acp"]

ACP_BACKENDS: dict[str, AcpBackendConfig] = {
    AcpBackendId.CLAUDE: AcpBackendConfig(
        id="claude",
        name="Claude Code",
        cli_command="claude",
        acp_args=DEFAULT_ACP_ARGS,
        auth_required=True,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.GEMINI: AcpBackendConfig(
        id="gemini",
        name="Google CLI",
        cli_command="gemini",
        acp_args=DEFAULT_ACP_ARGS,
        auth_required=True,
        enabled=False,
        supports_streaming=True,
    ),
    AcpBackendId.QWEN: AcpBackendConfig(
        id="qwen",
        name="Qwen Code",
        cli_command="qwen",
        default_cli_path="npx @qwen-code/qwen-code",
        acp_args=DEFAULT_ACP_ARGS,
        auth_required=True,
        enabled=True,
        supports_streaming=True,
    ),
    AcpBackendId.CODEX: AcpBackendConfig(
        id="codex",
        name="Codex",
        cli_command="codex",
        acp_args=DEFAULT_ACP_ARGS,
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.GOOSE: AcpBackendConfig(
        id="goose",
        name="Goose",
        cli_command="goose",
        acp_args=["acp"],
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.AUGGIE: AcpBackendConfig(
        id="auggie",
        name="Augment Code",
        cli_command="auggie",
        acp_args=["--acp"],
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.KIMI: AcpBackendConfig(
        id="kimi",
        name="Kimi CLI",
        cli_command="kimi",
        acp_args=["--acp"],
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.OPENCODE: AcpBackendConfig(
        id="opencode",
        name="OpenCode",
        cli_command="opencode",
        acp_args=["acp"],
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.IFLOW: AcpBackendConfig(
        id="iflow",
        name="iFlow CLI",
        cli_command="iflow",
        acp_args=DEFAULT_ACP_ARGS,
        auth_required=True,
        enabled=True,
        supports_streaming=False,
    ),
    AcpBackendId.CUSTOM: AcpBackendConfig(
        id="custom",
        name="Custom Agent",
        cli_command=None,
        acp_args=[],
        auth_required=False,
        enabled=True,
        supports_streaming=False,
    ),
}


def get_backend_config(backend_id: str) -> AcpBackendConfig | None:
    return ACP_BACKENDS.get(backend_id)


def get_enabled_backends() -> list[AcpBackendConfig]:
    return [cfg for cfg in ACP_BACKENDS.values() if cfg.enabled]


def get_cli_args(backend_id: str, cli_path: str | None = None) -> tuple[str, list[str]]:
    config = get_backend_config(backend_id)
    if not config:
        raise ValueError(f"Unknown backend: {backend_id}")

    path = cli_path or config.default_cli_path or config.cli_command
    if not path:
        raise ValueError(f"No CLI path for backend: {backend_id}")

    if path.startswith("npx "):
        parts = path.split()
        command = "npx"
        args = parts[1:] + config.acp_args
    else:
        command = path
        args = list(config.acp_args)

    return command, args
