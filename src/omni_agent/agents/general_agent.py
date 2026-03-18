"""
通用 Agent

配置了完整工具集的通用 Agent，支持 MCP 工具加载
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from omni_agent.core.agent import Agent
from omni_agent.core.llm_client import LLMClient
from omni_agent.skills.skill_loader import SkillLoader
from omni_agent.skills.skill_tool import GetSkillTool
from omni_agent.tools.base import Tool
from omni_agent.tools.bash_tool import BashTool
from omni_agent.tools.file_tools import (
    EditTool,
    GlobTool,
    GrepTool,
    ListDirTool,
    ReadTool,
    WriteTool,
)
from omni_agent.tools.mcp_loader import load_mcp_tools_async
from omni_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
from omni_agent.tools.user_input_tool import GetUserInputTool

GENERAL_SYSTEM_PROMPT = """你是一个功能强大的AI助手。

你拥有以下能力：
- 文件操作：读取、写入、编辑、搜索文件
- 命令执行：运行 shell 命令
- 网络搜索：通过 web_search_exa 搜索信息
- 网页抓取：通过 firecrawl 抓取和解析网页内容
- 地图服务：通过高德地图API获取地理信息

工作原则：
- 理解用户需求后再行动
- 合理使用工具完成任务
- 保持输出简洁清晰
"""


@dataclass
class LLMConfig:
    """LLM 配置"""

    model: str = "openai/gpt-4o"
    api_key: str | None = None
    api_base: str | None = None
    timeout: float = 120.0


@dataclass
class GeneralAgentConfig:
    """通用 Agent 配置"""

    llm: LLMConfig | None = None
    workspace_dir: str = "./workspace"
    mcp_config_path: str | None = "mcp.json"
    skills_dir: str | None = None
    max_steps: int = 50
    token_limit: int = 120000
    enable_user_input: bool = True
    enable_notes: bool = True
    system_prompt: str | None = None
    extra_tools: list[Tool] = field(default_factory=list)


def _create_file_tools(workspace_dir: str) -> list[Tool]:
    """创建文件操作工具"""
    ws = str(Path(workspace_dir).absolute())
    Path(ws).mkdir(parents=True, exist_ok=True)

    return [
        ReadTool(workspace_dir=ws),
        WriteTool(workspace_dir=ws),
        EditTool(workspace_dir=ws),
        ListDirTool(workspace_dir=ws),
        GlobTool(workspace_dir=ws),
        GrepTool(workspace_dir=ws),
        BashTool(),
    ]


def _create_note_tools(workspace_dir: str) -> list[Tool]:
    """创建笔记工具"""
    memory_file = str(Path(workspace_dir) / ".agent_memory.json")
    return [
        SessionNoteTool(memory_file=memory_file),
        RecallNoteTool(memory_file=memory_file),
    ]


async def _load_mcp_tools(mcp_config_path: str) -> list[Tool]:
    """加载 MCP 工具"""
    if not Path(mcp_config_path).exists():
        return []

    try:
        tools = await load_mcp_tools_async(mcp_config_path)
        return tools or []
    except Exception:
        return []


def _load_skills(skills_dir: str) -> tuple[SkillLoader | None, list[Tool]]:
    """加载 Skills"""
    if not skills_dir or not Path(skills_dir).exists():
        return None, []

    loader = SkillLoader(skills_dir)
    loader.discover_skills()

    if not loader.loaded_skills:
        return None, []

    return loader, [GetSkillTool(loader)]


def _build_system_prompt(
    base_prompt: str,
    skill_loader: SkillLoader | None,
    workspace_dir: str,
) -> str:
    """构建系统提示"""
    prompt = base_prompt

    if skill_loader:
        metadata = skill_loader.get_skills_metadata_prompt()
        if metadata:
            prompt = f"{prompt}\n\n{metadata}"

    workspace_info = (
        f"\n\n## 工作目录\n"
        f"当前工作目录: `{Path(workspace_dir).absolute()}`\n"
        f"所有相对路径将基于此目录解析。"
    )
    prompt = f"{prompt}{workspace_info}"

    return prompt


def _create_llm_client(llm_config: LLMConfig) -> LLMClient:
    """根据配置创建 LLM 客户端"""
    import os

    api_key = llm_config.api_key or os.getenv("LLM_API_KEY", "")
    if not api_key:
        raise ValueError(
            "LLM API key is required. Set via LLMConfig.api_key or LLM_API_KEY env var"
        )

    return LLMClient(
        api_key=api_key,
        api_base=llm_config.api_base,
        model=llm_config.model,
        timeout=llm_config.timeout,
    )


async def create_general_agent(
    llm_client: LLMClient | None = None,
    config: GeneralAgentConfig | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Agent:
    """
    创建通用 Agent

    配置：
    - 文件操作工具 (read, write, edit, list, glob, grep)
    - Bash 命令执行
    - MCP 工具 (exa search, firecrawl, amap)
    - 笔记工具 (可选)
    - Skills (可选)
    - 用户输入工具 (可选)

    Args:
        llm_client: LLM 客户端，如果不传则从 config.llm 创建
        config: Agent 配置，默认使用 GeneralAgentConfig()
        user_id: 用户 ID
        session_id: 会话 ID

    Returns:
        配置好的 Agent 实例
    """
    if config is None:
        config = GeneralAgentConfig()

    if llm_client is None:
        if config.llm is None:
            config.llm = LLMConfig()
        llm_client = _create_llm_client(config.llm)

    tools: list[Tool] = []

    tools.extend(_create_file_tools(config.workspace_dir))

    if config.enable_notes:
        tools.extend(_create_note_tools(config.workspace_dir))

    if config.enable_user_input:
        tools.append(GetUserInputTool())

    if config.mcp_config_path:
        mcp_tools = await _load_mcp_tools(config.mcp_config_path)
        tools.extend(mcp_tools)

    skill_loader = None
    if config.skills_dir:
        skill_loader, skill_tools = _load_skills(config.skills_dir)
        tools.extend(skill_tools)

    if config.extra_tools:
        tools.extend(config.extra_tools)

    base_prompt = config.system_prompt or GENERAL_SYSTEM_PROMPT
    system_prompt = _build_system_prompt(base_prompt, skill_loader, config.workspace_dir)

    return Agent(
        llm_client=llm_client,
        name="general",
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.max_steps,
        workspace_dir=config.workspace_dir,
        token_limit=config.token_limit,
        skill_loader=skill_loader,
        user_id=user_id,
        session_id=session_id,
    )


def create_general_agent_sync(
    llm_client: LLMClient | None = None,
    config: GeneralAgentConfig | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Agent:
    """
    同步版本的 create_general_agent

    在非异步上下文中使用
    """
    return asyncio.run(create_general_agent(llm_client, config, user_id, session_id))
