"""文档处理器，用于解析和分块文件。"""

from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader

from omni_agent.core.config import settings


class DocumentProcessor:
    """处理文档：解析内容并分块。"""

    SUPPORTED_TYPES = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
    }

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def get_file_type(self, filename: str) -> str | None:
        """从文件名扩展名获取文件类型。"""
        suffix = Path(filename).suffix.lower()
        return self.SUPPORTED_TYPES.get(suffix)

    def is_supported(self, filename: str) -> bool:
        """检查文件类型是否支持。"""
        return self.get_file_type(filename) is not None

    async def extract_text(self, file: BinaryIO, filename: str) -> str:
        """从文件中提取文本内容。"""
        file_type = self.get_file_type(filename)

        if file_type == "application/pdf":
            return self._extract_pdf(file)
        elif file_type in ("text/plain", "text/markdown"):
            return self._extract_text(file)
        else:
            raise ValueError(f"Unsupported file type: {filename}")

    def _extract_text(self, file: BinaryIO) -> str:
        """从纯文本或 markdown 文件中提取文本。"""
        content = file.read()
        if isinstance(content, bytes):
            # Try UTF-8 first, fallback to other encodings
            for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError("Unable to decode file content")
        return content

    def _extract_pdf(self, file: BinaryIO) -> str:
        """从 PDF 文件中提取文本。"""
        reader = PdfReader(file)
        text_parts: list[str] = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n\n".join(text_parts)

    def chunk_text(self, text: str) -> list[dict]:
        """将文本分割成重叠的分块。"""
        if not text.strip():
            return []

        # Clean text: normalize whitespace
        text = " ".join(text.split())

        chunks: list[dict] = []
        start = 0
        chunk_index = 0

        while start < len(text):
            # Get chunk end position
            end = start + self.chunk_size

            # If not at end of text, try to break at sentence/word boundary
            if end < len(text):
                # Look for sentence boundary (. ! ?)
                for sep in [". ", "! ", "? ", "\n", "。", "！", "？"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break
                else:
                    # Fall back to word boundary (space)
                    last_space = text.rfind(" ", start, end)
                    if last_space > start:
                        end = last_space + 1

            chunk_content = text[start:end].strip()

            if chunk_content:
                chunks.append(
                    {
                        "content": chunk_content,
                        "chunk_index": chunk_index,
                        "metadata": {
                            "start_char": start,
                            "end_char": end,
                        },
                    }
                )
                chunk_index += 1

            # Move start position with overlap
            start = end - self.chunk_overlap
            if start >= len(text) - self.chunk_overlap:
                break

        return chunks

    async def process_file(
        self,
        file: BinaryIO,
        filename: str,
    ) -> tuple[str, list[dict]]:
        """处理文件：提取文本并分块。

        Returns:
            (完整文本, 分块列表) 的元组
        """
        text = await self.extract_text(file, filename)
        chunks = self.chunk_text(text)
        return text, chunks


# 全局文档处理器实例
document_processor = DocumentProcessor()
