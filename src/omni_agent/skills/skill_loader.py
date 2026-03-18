"""
Skill Loader - 加载 Claude Skills 实现 Progressive Disclosure

支持从 SKILL.md 文件加载技能并提供给 Agent
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """Skill 数据结构"""

    name: str
    description: str
    content: str
    license: str | None = None
    allowed_tools: list[str] | None = None
    metadata: dict[str, str] | None = None
    skill_path: Path | None = None

    def to_prompt(self) -> str:
        """转换 skill 为 prompt 格式"""
        return f"""
# Skill: {self.name}

{self.description}

---

{self.content}
"""


class SkillLoader:
    """Skill 加载器"""

    def __init__(self, skills_dir: str = "src/omni_agent/skills") -> None:
        """
        初始化 Skill Loader

        Args:
            skills_dir: Skills 目录路径
        """
        self.skills_dir = Path(skills_dir)
        self.loaded_skills: dict[str, Skill] = {}

    def load_skill(self, skill_path: Path) -> Skill | None:
        """
        从 SKILL.md 文件加载单个 skill

        Args:
            skill_path: SKILL.md 文件路径

        Returns:
            Skill 对象，如果加载失败返回 None
        """
        try:
            content = skill_path.read_text(encoding="utf-8")

            # 解析 YAML frontmatter
            frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)

            if not frontmatter_match:
                logger.warning("Skill %s missing YAML frontmatter", skill_path)
                return None

            frontmatter_text = frontmatter_match.group(1)
            skill_content = frontmatter_match.group(2).strip()

            # 解析 YAML
            try:
                frontmatter = yaml.safe_load(frontmatter_text)
            except yaml.YAMLError as e:
                logger.error("Failed to parse YAML frontmatter in %s: %s", skill_path, e)
                return None

            if "name" not in frontmatter or "description" not in frontmatter:
                logger.warning("Skill %s missing required fields (name or description)", skill_path)
                return None

            # 获取 skill 目录（SKILL.md 的父目录）
            skill_dir = skill_path.parent

            # 处理内容中的相对路径，转换为绝对路径
            processed_content = self._process_skill_paths(skill_content, skill_dir)

            # 创建 Skill 对象
            skill = Skill(
                name=frontmatter["name"],
                description=frontmatter["description"],
                content=processed_content,
                license=frontmatter.get("license"),
                allowed_tools=frontmatter.get("allowed-tools"),
                metadata=frontmatter.get("metadata"),
                skill_path=skill_path,
            )

            return skill

        except Exception as e:
            logger.error("Failed to load skill from %s: %s", skill_path, e)
            return None

    def _process_skill_paths(self, content: str, skill_dir: Path) -> str:
        """
        处理 skill 内容，将相对路径替换为绝对路径

        支持 Progressive Disclosure Level 3+: 将相对文件引用转换为绝对路径
        以便 Agent 可以轻松读取嵌套资源

        Args:
            content: 原始 skill 内容
            skill_dir: Skill 目录路径

        Returns:
            处理后的内容（包含绝对路径）
        """

        # Pattern 1: 基于目录的路径 (scripts/, examples/, templates/, reference/)
        def replace_dir_path(match: re.Match[str]) -> str:
            prefix = match.group(1)  # 例如 "python " 或 "`"
            rel_path = match.group(2)  # 例如 "scripts/with_server.py"

            abs_path = skill_dir / rel_path
            if abs_path.exists():
                return f"{prefix}{abs_path}"
            return match.group(0)

        pattern_dirs = r"(python\s+|`)((?:scripts|examples|templates|reference)/[^\s`\)]+)"
        content = re.sub(pattern_dirs, replace_dir_path, content)

        # Pattern 2: 直接文档引用 (forms.md, reference.md, 等)
        # 匹配类似 "see reference.md" 或 "read forms.md" 的短语
        def replace_doc_path(match: re.Match[str]) -> str:
            prefix = match.group(1)  # 例如 "see ", "read "
            filename = match.group(2)  # 例如 "reference.md"
            suffix = match.group(3)  # 例如标点符号

            abs_path = skill_dir / filename
            if abs_path.exists():
                # 为 Agent 添加有用的指令
                return f"{prefix}`{abs_path}` (use read_file to access){suffix}"
            return match.group(0)

        # 匹配模式如: "see reference.md" 或 "read forms.md"
        pattern_docs = (
            r"(see|read|refer to|check)\s+([a-zA-Z0-9_-]+\.(?:md|txt|json|yaml))([.,;\s])"
        )
        content = re.sub(pattern_docs, replace_doc_path, content, flags=re.IGNORECASE)

        # Pattern 3: Markdown 链接 - 支持多种格式:
        # - [`filename.md`](filename.md) - 简单文件名
        # - [text](./reference/file.md) - 带 ./ 的相对路径
        # - [text](scripts/file.js) - 基于目录的路径
        def replace_markdown_link(match: re.Match[str]) -> str:
            prefix = match.group(1) if match.group(1) else ""  # 例如 "Read ", "Load ", 或空
            link_text = match.group(2)  # 例如 "`docx-js.md`" 或 "Guide"
            filepath = match.group(3)  # 例如 "docx-js.md", "./reference/file.md"

            # 移除开头的 ./ (如果存在)
            clean_path = filepath[2:] if filepath.startswith("./") else filepath

            abs_path = skill_dir / clean_path
            if abs_path.exists():
                # 保留链接文本样式（带或不带反引号）
                return f"{prefix}[{link_text}](`{abs_path}`) (use read_file to access)"
            return match.group(0)

        # 匹配 markdown 链接模式，可选前缀词
        pattern_markdown = (
            r"(?:(Read|See|Check|Refer to|Load|View)\s+)?"
            r"\[(`?[^`\]]+`?)\]"
            r"\(((?:\./)?[^)]+\.(?:md|txt|json|yaml|js|py|html))\)"
        )
        content = re.sub(pattern_markdown, replace_markdown_link, content, flags=re.IGNORECASE)

        return content

    def discover_skills(self) -> list[Skill]:
        """
        发现并加载 skills 目录中的所有 skills

        Returns:
            Skills 列表
        """
        skills = []

        if not self.skills_dir.exists():
            logger.warning("Skills directory not found: %s", self.skills_dir)
            return skills

        # 递归查找所有 SKILL.md 文件
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            skill = self.load_skill(skill_file)
            if skill:
                skills.append(skill)
                self.loaded_skills[skill.name] = skill

        return skills

    def get_skill(self, name: str) -> Skill | None:
        """
        获取已加载的 skill

        Args:
            name: Skill 名称

        Returns:
            Skill 对象，如果未找到返回 None
        """
        return self.loaded_skills.get(name)

    def list_skills(self) -> list[str]:
        """
        列出所有已加载的 skill 名称

        Returns:
            Skill 名称列表
        """
        return list(self.loaded_skills.keys())

    def get_skills_metadata_prompt(self) -> str:
        """
        生成仅包含元数据（名称 + 描述）的 prompt，用于所有 skills
        这实现了 Progressive Disclosure - Level 1

        Returns:
            仅元数据的 prompt 字符串
        """
        if not self.loaded_skills:
            return ""

        prompt_parts = ["## Available Skills\n"]
        prompt_parts.append(
            "You have access to specialized skills. Each skill provides expert guidance for specific tasks.\n"
        )
        prompt_parts.append("Load a skill's full content using the `get_skill` tool when needed.\n")

        # 列出所有 skills 及其描述
        for skill in self.loaded_skills.values():
            prompt_parts.append(f"- `{skill.name}`: {skill.description}")

        return "\n".join(prompt_parts)
