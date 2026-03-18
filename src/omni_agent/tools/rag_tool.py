"""RAG 工具，用于搜索知识库。"""

from typing import Any

from omni_agent.core.config import settings
from omni_agent.rag.rag_service import rag_service
from omni_agent.tools.base import Tool, ToolResult


class RAGTool(Tool):
    """使用混合检索搜索知识库的工具。"""

    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def description(self) -> str:
        return (
            "Search the knowledge base for relevant information. "
            "Use this tool when you need to find information from uploaded documents. "
            "Uses hybrid search (semantic + keyword) by default for best results."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information",
                },
                "top_k": {
                    "type": "integer",
                    "description": f"Number of results to return (default: {settings.RAG_TOP_K})",
                    "default": settings.RAG_TOP_K,
                },
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "semantic", "keyword"],
                    "description": "Search mode: hybrid (default), semantic, or keyword",
                    "default": "hybrid",
                },
            },
            "required": ["query"],
        }

    @property
    def instructions(self) -> str | None:
        return """
When using the search_knowledge tool:
- Uses hybrid search (semantic + keyword) by default for best results
- Use specific, descriptive queries for better results
- The tool returns text chunks with relevance scores
- Higher scores indicate more relevant content
- Consider searching with different phrasings if initial results are not helpful
- Use mode="keyword" for exact term matching
- Use mode="semantic" for conceptual similarity only
"""

    @property
    def add_instructions_to_prompt(self) -> bool:
        return True

    async def execute(
        self, query: str, top_k: int | None = None, mode: str = "hybrid"
    ) -> ToolResult:
        """执行知识库搜索。"""
        try:
            results = await rag_service.search(
                query=query,
                top_k=top_k or settings.RAG_TOP_K,
                mode=mode,
            )

            if not results:
                return ToolResult(
                    success=True,
                    content="No relevant information found in the knowledge base.",
                )

            # Format results
            formatted_results: list[str] = []
            for i, result in enumerate(results, 1):
                similarity_pct = result["similarity"] * 100
                formatted_results.append(
                    f"[{i}] (Similarity: {similarity_pct:.1f}%) "
                    f"From: {result['filename']}\n"
                    f"{result['content']}\n"
                )

            content = f"Found {len(results)} relevant results:\n\n" + "\n---\n".join(
                formatted_results
            )

            return ToolResult(success=True, content=content)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Knowledge base search failed: {str(e)}",
            )
