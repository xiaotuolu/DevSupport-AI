# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""文档中心接口：向已登录用户提供知识库原始资料的浏览能力。

资料来源为项目根目录 data/knowledge/*.md（与 RAG 检索同一份源）。
"""

from fastapi import APIRouter, Depends, HTTPException

from app.deps import CurrentUser, get_current_user
from app.rag.ingest import CATEGORY_MAP, KNOWLEDGE_DIR

router = APIRouter(prefix="/api/docs", tags=["docs"])


def _meta(path):
    """从文件名前缀取 id/分类，从首行 markdown 标题取标题。"""
    stem = path.stem
    prefix = stem.split("-")[0]
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else stem
    title = first[2:].strip() if first.startswith("# ") else stem
    return {
        "id": prefix,
        "title": title,
        "category": CATEGORY_MAP.get(prefix, "其它"),
        "filename": path.name,
    }


@router.get("")
async def list_docs(user: CurrentUser = Depends(get_current_user)) -> dict:
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    return {"documents": [_meta(f) for f in files]}


@router.get("/{doc_id}")
async def get_doc(doc_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    matches = list(KNOWLEDGE_DIR.glob(f"{doc_id}-*.md"))
    if not matches:
        raise HTTPException(404, "文档不存在")
    path = matches[0]
    meta = _meta(path)
    meta["content"] = path.read_text(encoding="utf-8")
    return meta
