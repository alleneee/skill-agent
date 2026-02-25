"""
Skill Tool - Agent 按需加载 Skills 的工具

实现 Progressive Disclosure (Level 2): 在需要时加载完整的 skill 内容
"""

import logging
from typing import Any

from omni_agent.skills.skill_loader import SkillLoader
from omni_agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class GetSkillTool(Tool):
    """获取指定 skill 详细信息的工具"""

    def __init__(self, skill_loader: SkillLoader) -> None:
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "get_skill"

    @property
    def description(self) -> str:
        return "Get complete content and guidance for a specified skill, used for executing specific types of tasks"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to retrieve (use the skill names from the Available Skills list in your system prompt)",
                }
            },
            "required": ["skill_name"],
        }

    async def execute(self, skill_name: str) -> ToolResult:
        """获取指定 skill 的详细信息"""
        skill = self.skill_loader.get_skill(skill_name)

        if not skill:
            available = ", ".join(self.skill_loader.list_skills())
            return ToolResult(
                success=False,
                content="",
                error=f"Skill '{skill_name}' does not exist. Available skills: {available}",
            )

        # 返回完整的 skill 内容
        result = skill.to_prompt()
        return ToolResult(success=True, content=result)


def create_skill_tools(
    skills_dir: str = "src/omni_agent/skills",
) -> tuple[list[Tool], SkillLoader | None]:
    """
    创建 Progressive Disclosure 的 skill 工具

    仅提供 get_skill 工具 - agents 使用系统提示中的元数据
    了解有哪些 skills 可用，然后按需加载它们

    Args:
        skills_dir: Skills 目录路径

    Returns:
        元组 (工具列表, skill loader)
    """
    # 创建 skill loader
    loader = SkillLoader(skills_dir)

    skills = loader.discover_skills()
    logger.info("Discovered %d skills", len(skills))

    if not skills:
        return [], None

    # 仅创建 get_skill 工具 (Progressive Disclosure Level 2)
    tools = [
        GetSkillTool(loader),
    ]

    return tools, loader
