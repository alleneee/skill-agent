"""RAG 服务，用于知识库操作。"""

from typing import Any, BinaryIO

from omni_agent.core.config import settings
from omni_agent.rag.database import DatabaseManager, db_manager
from omni_agent.rag.document_processor import DocumentProcessor, document_processor
from omni_agent.rag.embedding_service import EmbeddingService, embedding_service


class RAGService:
    """RAG 操作的高级服务。"""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        embedder: EmbeddingService | None = None,
        processor: DocumentProcessor | None = None,
    ) -> None:
        self.db = db or db_manager
        self.embedder = embedder or embedding_service
        self.processor = processor or document_processor

    async def initialize(self) -> None:
        """初始化 RAG 服务（连接数据库并创建模式）。"""
        await self.db.connect()
        await self.db.initialize_schema()

    async def shutdown(self) -> None:
        """关闭 RAG 服务。"""
        await self.db.disconnect()

    async def add_document(
        self,
        file: BinaryIO,
        filename: str,
        file_size: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将文档添加到知识库。

        Returns:
            包含 id 和分块数量的文档信息
        """
        # Validate file type
        if not self.processor.is_supported(filename):
            raise ValueError(
                f"Unsupported file type. Supported: {list(self.processor.SUPPORTED_TYPES.keys())}"
            )

        file_type = self.processor.get_file_type(filename)

        # Process file: extract text and chunk
        _, chunks = await self.processor.process_file(file, filename)

        if not chunks:
            raise ValueError("No content could be extracted from the file")

        # Generate embeddings for all chunks
        chunk_texts = [chunk["content"] for chunk in chunks]
        embeddings = await self.embedder.embed_texts(chunk_texts)

        # Add embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            chunk["embedding"] = embedding

        # Store in database
        doc_id = await self.db.insert_document(
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            metadata=metadata,
        )

        await self.db.insert_chunks(doc_id, chunks)

        return {
            "id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
            "chunk_count": len(chunks),
        }

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: str = "hybrid",
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[dict[str, Any]]:
        """搜索知识库中的相关内容。

        Args:
            query: 搜索查询文本
            top_k: 返回结果数量（默认来自设置）
            mode: 搜索模式 - "hybrid"（默认）、"semantic" 或 "keyword"
            semantic_weight: 混合模式中语义搜索的权重 (0-1)
            keyword_weight: 混合模式中关键词搜索的权重 (0-1)

        Returns:
            带有分数的相关分块列表
        """
        top_k = top_k or settings.RAG_TOP_K

        if mode == "keyword":
            # Pure keyword search
            results = await self.db.search_keyword(query=query, top_k=top_k)
            # Normalize output format
            for r in results:
                r["similarity"] = r.pop("rank", 0)
            return results

        # Generate query embedding for semantic/hybrid search
        query_embedding = await self.embedder.embed_text(query)

        if mode == "semantic":
            # Pure semantic search
            return await self.db.search_similar(
                query_embedding=query_embedding,
                top_k=top_k,
            )

        # Default: Hybrid search (semantic + keyword with RRF)
        results = await self.db.search_hybrid(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

        # Add unified similarity score based on RRF
        for r in results:
            r["similarity"] = r["rrf_score"]

        return results

    async def list_documents(self) -> list[dict[str, Any]]:
        """列出知识库中的所有文档。"""
        return await self.db.list_documents()

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        """按 ID 获取文档。"""
        return await self.db.get_document(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """从知识库中删除文档。"""
        return await self.db.delete_document(document_id)


# 全局 RAG 服务实例
rag_service = RAGService()
