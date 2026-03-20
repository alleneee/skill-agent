"""Memory Tools - 深度记忆检索工具

Agent 通过 file tools + memory-management skill 直接操作 .md 文件，
此模块仅保留 DeepRecallMemoryTool 用于语义/关键词混合搜索。
"""

import logging
from typing import Any

from omni_agent.core.memory import Memory
from omni_agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class DeepRecallMemoryTool(Tool):
    """深度记忆检索 - 通过语义搜索和关键词搜索获取记忆内容"""

    def __init__(
        self,
        memory: Memory,
        user_id: str,
        session_id: str,
    ):
        self._memory = memory
        self._user_id = user_id
        self._session_id = session_id
        self._embedding_service: Any = None
        self._vector_store: Any = None

    @property
    def name(self) -> str:
        return "deep_recall_memory"

    @property
    def description(self) -> str:
        return (
            "深度检索用户记忆内容。"
            "搜索 profile(用户画像)、habit(用户习惯)、context(会话上下文) 三个维度。"
            "支持语义搜索和关键词搜索。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本",
                },
                "memory_type": {
                    "type": "string",
                    "description": "按类型过滤",
                    "enum": ["profile", "habit", "context"],
                },
                "mode": {
                    "type": "string",
                    "description": "搜索模式: semantic(语义), keyword(关键词), hybrid(混合，默认)",
                    "enum": ["semantic", "keyword", "hybrid"],
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认 5",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        }

    def _get_embedding_service(self) -> Any:
        if self._embedding_service is None:
            try:
                from omni_agent.rag.embedding_service import embedding_service

                self._embedding_service = embedding_service
            except Exception:
                logging.getLogger(__name__).debug("Embedding service unavailable", exc_info=True)
        return self._embedding_service

    def _get_vector_store(self) -> Any:
        if self._vector_store is None:
            try:
                from omni_agent.core.memory_vector import MemoryVectorStore

                self._vector_store = MemoryVectorStore(self._user_id, self._session_id)
            except Exception:
                logging.getLogger(__name__).debug("Vector store unavailable", exc_info=True)
        return self._vector_store

    async def execute(
        self,
        query: str = "",
        memory_type: str = "",
        mode: str = "hybrid",
        limit: int = 5,
    ) -> ToolResult:
        try:
            if not query:
                return ToolResult(
                    success=False,
                    content="",
                    error="请提供 query 参数",
                )

            keyword_results = self._keyword_search(query, memory_type, limit)

            semantic_results: list[dict] = []
            if mode in ("semantic", "hybrid"):
                semantic_results = await self._semantic_search(query, memory_type, limit)

            if mode == "semantic":
                results = semantic_results
            elif mode == "keyword":
                results = keyword_results
            else:
                results = self._merge_results(semantic_results, keyword_results, limit)

            if not results:
                return ToolResult(
                    success=True,
                    content=f"没有找到与 '{query}' 相关的记忆。",
                )

            lines = [f"找到 {len(results)} 条相关记忆:\n"]
            for i, mem in enumerate(results, 1):
                sim = mem.get("similarity")
                sim_str = f" (相似度: {sim:.2f})" if sim is not None else ""
                mem_type_str = mem.get("type", "unknown")
                content = mem.get("content", "")
                lines.append(f"{i}. [{mem_type_str}]{sim_str}\n   {content}")

            return ToolResult(
                success=True,
                content="\n".join(lines),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"深度检索记忆失败: {e}",
            )

    def _keyword_search(self, query: str, memory_type: str, limit: int) -> list[dict]:
        sources: dict[str, str] = {}
        if not memory_type or memory_type == "profile":
            sources["profile"] = self._memory.read_profile()
        if not memory_type or memory_type == "habit":
            sources["habit"] = self._memory.read_habit()
        if not memory_type or memory_type == "context":
            sources["context"] = self._memory.read_context()

        query_lower = query.lower()
        scored: list[tuple[float, dict]] = []

        for src_type, content in sources.items():
            if not content:
                continue
            paragraphs = self._split_paragraphs(content)
            for para in paragraphs:
                if query_lower in para.lower():
                    score = 1.0 if query_lower in para.lower().split("\n")[0] else 0.8
                    scored.append(
                        (
                            score,
                            {
                                "type": src_type,
                                "content": para.strip(),
                                "similarity": score,
                            },
                        )
                    )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _split_paragraphs(self, content: str) -> list[str]:
        """按段落切分 .md 内容，以 markdown 标题或列表项为分界"""
        lines = content.split("\n")
        paragraphs: list[str] = []
        current: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current:
                    paragraphs.append("\n".join(current))
                    current = []
                continue
            if (stripped.startswith("# ") or stripped.startswith("## ")) and current:
                paragraphs.append("\n".join(current))
                current = []
            current.append(line)

        if current:
            paragraphs.append("\n".join(current))

        return paragraphs

    async def _semantic_search(self, query: str, memory_type: str, limit: int) -> list[dict]:
        embedding_service = self._get_embedding_service()
        vector_store = self._get_vector_store()

        if not embedding_service or not vector_store:
            return []

        try:
            embedding = await embedding_service.embed_text(query)
            results = await vector_store.search(
                embedding=embedding,
                memory_type=memory_type or None,
                threshold=0.5,
                top_k=limit,
            )

            return [
                {
                    "type": mem_type,
                    "similarity": similarity,
                    "content": content,
                }
                for _, mem_type, similarity, content in results
            ]
        except Exception as e:
            logger.warning(f"语义搜索失败: {e}")
            return []

    def _merge_results(
        self,
        semantic: list[dict],
        keyword: list[dict],
        limit: int,
    ) -> list[dict]:
        seen_content: set[str] = set()
        merged: list[tuple[float, dict]] = []

        for mem in semantic:
            content_key = mem.get("content", "")[:80]
            sim = mem.get("similarity", 0.0)
            merged.append((sim, mem))
            seen_content.add(content_key)

        for mem in keyword:
            content_key = mem.get("content", "")[:80]
            if content_key in seen_content:
                continue
            kw_score = mem.get("similarity", 0.0) * 0.7
            merged.append((kw_score, mem))
            seen_content.add(content_key)

        merged.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in merged[:limit]]


def create_memory_tools(
    memory: Memory,
    user_id: str = "",
    session_id: str = "",
) -> list[Tool]:
    """创建记忆工具实例"""
    tools: list[Tool] = []
    if user_id and session_id:
        tools.append(DeepRecallMemoryTool(memory, user_id, session_id))
    return tools
