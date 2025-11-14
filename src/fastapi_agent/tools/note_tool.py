"""Session Note Tool - 让 agent 记录和回忆重要信息

这个工具允许 agent:
- 在会话期间记录关键点和重要信息
- 回忆之前记录的笔记
- 跨 agent 执行链维护上下文
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi_agent.tools.base import Tool, ToolResult


class SessionNoteTool(Tool):
    """用于记录会话笔记的工具

    Agent 可以使用这个工具来:
    - 记录重要的事实、决策或上下文
    - 回忆之前会话的信息
    - 随时间积累知识

    使用示例:
    - record_note("用户偏好简洁的回复")
    - record_note("项目使用 Python 3.12 和 async/await")
    - recall_notes() -> 检索所有记录的笔记
    """

    def __init__(self, memory_file: str = "./workspace/.agent_memory.json"):
        """初始化会话笔记工具

        Args:
            memory_file: 笔记存储文件的路径
        """
        self.memory_file = Path(memory_file)
        # 延迟加载：文件和目录只在第一次记录笔记时创建

    @property
    def name(self) -> str:
        return "record_note"

    @property
    def description(self) -> str:
        return (
            "记录重要信息作为会话笔记，以便将来参考。"
            "使用此工具记录关键事实、用户偏好、决策或上下文，"
            "这些信息应在 agent 执行链中稍后回忆。每个笔记都会带有时间戳。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要记录为笔记的信息。简洁但具体。",
                },
                "category": {
                    "type": "string",
                    "description": "此笔记的可选分类/标签（例如：'user_preference'、'project_info'、'decision'）",
                },
            },
            "required": ["content"],
        }

    def _load_from_file(self) -> list:
        """从文件加载笔记

        如果文件不存在则返回空列表（延迟加载）
        """
        if not self.memory_file.exists():
            return []

        try:
            return json.loads(self.memory_file.read_text(encoding='utf-8'))
        except Exception:
            return []

    def _save_to_file(self, notes: list):
        """保存笔记到文件

        如果父目录和文件不存在则创建（延迟初始化）
        """
        # 在实际保存时确保父目录存在
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(
            json.dumps(notes, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    async def execute(self, content: str, category: str = "general") -> ToolResult:
        """记录一条会话笔记

        Args:
            content: 要记录的信息
            category: 此笔记的分类/标签

        Returns:
            带有成功状态的 ToolResult
        """
        try:
            # 加载现有笔记
            notes = self._load_from_file()

            # 添加新笔记和时间戳
            note = {
                "timestamp": datetime.now().isoformat(),
                "category": category,
                "content": content,
            }
            notes.append(note)

            # 保存回文件
            self._save_to_file(notes)

            return ToolResult(
                success=True,
                content=f"已记录笔记: {content} (分类: {category})",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"记录笔记失败: {str(e)}",
            )


class RecallNoteTool(Tool):
    """用于回忆已记录会话笔记的工具"""

    def __init__(self, memory_file: str = "./workspace/.agent_memory.json"):
        """初始化回忆笔记工具

        Args:
            memory_file: 笔记存储文件的路径
        """
        self.memory_file = Path(memory_file)

    @property
    def name(self) -> str:
        return "recall_notes"

    @property
    def description(self) -> str:
        return (
            "回忆所有之前记录的会话笔记。"
            "使用此工具检索重要信息、上下文或决策，"
            "这些信息来自会话早期或之前的 agent 执行链。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "可选：按分类筛选笔记",
                },
            },
        }

    async def execute(self, category: str = None) -> ToolResult:
        """回忆会话笔记

        Args:
            category: 可选的分类过滤器

        Returns:
            带有笔记内容的 ToolResult
        """
        try:
            if not self.memory_file.exists():
                return ToolResult(
                    success=True,
                    content="尚未记录任何笔记。",
                )

            notes = json.loads(self.memory_file.read_text(encoding='utf-8'))

            if not notes:
                return ToolResult(
                    success=True,
                    content="尚未记录任何笔记。",
                )

            # 如果指定了分类则过滤
            if category:
                notes = [n for n in notes if n.get("category") == category]
                if not notes:
                    return ToolResult(
                        success=True,
                        content=f"未找到分类为 '{category}' 的笔记",
                    )

            # 格式化笔记用于显示
            formatted = []
            for idx, note in enumerate(notes, 1):
                timestamp = note.get("timestamp", "未知时间")
                cat = note.get("category", "general")
                content = note.get("content", "")
                formatted.append(
                    f"{idx}. [{cat}] {content}\n   (记录于 {timestamp})"
                )

            result = "已记录的笔记:\n" + "\n".join(formatted)

            return ToolResult(success=True, content=result)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"回忆笔记失败: {str(e)}",
            )
