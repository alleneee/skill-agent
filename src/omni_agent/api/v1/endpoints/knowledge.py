"""知识库管理 API 端点。"""

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from omni_agent.rag.rag_service import rag_service

router = APIRouter()


class DocumentResponse(BaseModel):
    """文档响应模型。"""

    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int


class DocumentListResponse(BaseModel):
    """文档列表响应模型。"""

    documents: list[dict[str, Any]]
    total: int


class SearchRequest(BaseModel):
    """搜索请求模型。"""

    query: str
    top_k: int = 5
    mode: str = "hybrid"  # "hybrid", "semantic", or "keyword"
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3


class SearchResult(BaseModel):
    """搜索结果模型。"""

    id: str
    content: str
    filename: str
    similarity: float


class SearchResponse(BaseModel):
    """搜索响应模型。"""

    results: list[SearchResult]
    total: int


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    """上传文档到知识库。

    支持格式: TXT, Markdown, PDF
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # 检查文件类型
    if not rag_service.processor.is_supported(file.filename):
        supported = list(rag_service.processor.SUPPORTED_TYPES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {supported}",
        )

    try:
        # 获取文件大小
        content = await file.read()
        file_size = len(content)

        # 重置文件位置以便处理
        await file.seek(0)

        # 将文档添加到知识库
        result = await rag_service.add_document(
            file=file.file,
            filename=file.filename,
            file_size=file_size,
        )

        return DocumentResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document: {str(e)}",
        )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """列出知识库中的所有文档。"""
    documents = await rag_service.list_documents()
    return DocumentListResponse(documents=documents, total=len(documents))


@router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict[str, Any]:
    """根据 ID 获取文档详情。"""
    document = await rag_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict[str, str]:
    """从知识库中删除文档。"""
    success = await rag_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted successfully"}


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest) -> SearchResponse:
    """在知识库中搜索相关内容。

    搜索模式:
    - hybrid (默认): 使用 RRF 融合语义搜索和关键词搜索
    - semantic: 纯向量相似度搜索
    - keyword: 纯全文搜索 (BM25 风格)
    """
    try:
        results = await rag_service.search(
            query=request.query,
            top_k=request.top_k,
            mode=request.mode,
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
        )

        search_results = [
            SearchResult(
                id=r["id"],
                content=r["content"],
                filename=r["filename"],
                similarity=r["similarity"],
            )
            for r in results
        ]

        return SearchResponse(results=search_results, total=len(search_results))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )
