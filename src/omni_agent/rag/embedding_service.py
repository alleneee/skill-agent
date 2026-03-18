"""嵌入服务，使用 DashScope API（OpenAI 兼容）。"""

from openai import AsyncOpenAI

from omni_agent.core.config import settings


class EmbeddingService:
    """使用 DashScope API 生成文本嵌入的服务。"""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """获取或创建 DashScope 的 OpenAI 客户端。"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.DASHSCOPE_API_KEY,
                base_url=settings.DASHSCOPE_API_BASE,
            )
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """为单个文本生成嵌入。"""
        client = self._get_client()
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """为多个文本生成嵌入（批量处理）。"""
        if not texts:
            return []

        client = self._get_client()

        # DashScope supports batch embedding
        # Process in batches of 25 to avoid rate limits
        batch_size = 25
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=batch,
            )
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])

        return all_embeddings


# 全局嵌入服务实例
embedding_service = EmbeddingService()
