# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Milvus 向量存储：knowledge_chunk collection 的管理与检索。

字段：
- pk           自增主键
- embedding    FLOAT_VECTOR(dim)，HNSW 索引，COSINE 度量
- content      原文片段
- doc_title    文档标题（引用 + 标量过滤）
- section      章节
- category     文档分类
- error_code   错误码（错误码类问题标量精确匹配）
- version      文档版本
"""

from functools import lru_cache

from pymilvus import DataType, MilvusClient

from app.config import settings

VECTOR_DIM = settings.embedding_dim
COLLECTION = settings.milvus_collection


@lru_cache
def get_client() -> MilvusClient:
    return MilvusClient(uri=settings.milvus_uri)


def ensure_collection(recreate: bool = False) -> None:
    """创建 collection（含 HNSW 索引）。recreate=True 时先删除重建。"""
    client = get_client()
    if recreate and client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
    if client.has_collection(COLLECTION):
        return

    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("pk", DataType.INT64, is_primary=True)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
    schema.add_field("content", DataType.VARCHAR, max_length=4000)
    schema.add_field("doc_title", DataType.VARCHAR, max_length=256)
    schema.add_field("section", DataType.VARCHAR, max_length=256)
    schema.add_field("category", DataType.VARCHAR, max_length=64)
    schema.add_field("error_code", DataType.VARCHAR, max_length=64)
    schema.add_field("version", DataType.VARCHAR, max_length=32)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    client.create_collection(
        collection_name=COLLECTION, schema=schema, index_params=index_params
    )


def drop_collection() -> None:
    client = get_client()
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)


def insert(rows: list[dict]) -> int:
    """批量插入切片。rows 每项含 embedding/content/doc_title/section/category/error_code/version。"""
    client = get_client()
    res = client.insert(collection_name=COLLECTION, data=rows)
    client.flush(COLLECTION)
    return res.get("insert_count", len(rows))


def count() -> int:
    client = get_client()
    if not client.has_collection(COLLECTION):
        return 0
    client.load_collection(COLLECTION)
    res = client.query(COLLECTION, filter="pk >= 0", output_fields=["count(*)"])
    if res and "count(*)" in res[0]:
        return res[0]["count(*)"]
    return 0


def all_chunks(limit: int = 2000) -> list[dict]:
    """取出全部切片（用于构建 BM25 关键词索引）。"""
    client = get_client()
    if not client.has_collection(COLLECTION):
        return []
    client.load_collection(COLLECTION)
    return client.query(
        COLLECTION,
        filter="pk >= 0",
        output_fields=["content", "doc_title", "section", "category", "error_code", "version"],
        limit=limit,
    )


def search(
    query_vector: list[float], top_k: int = 20, expr: str | None = None
) -> list[dict]:
    """向量检索，返回片段 + 相似度分数（COSINE，越大越相似）。"""
    client = get_client()
    client.load_collection(COLLECTION)
    results = client.search(
        collection_name=COLLECTION,
        data=[query_vector],
        limit=top_k,
        filter=expr or "",
        output_fields=["content", "doc_title", "section", "category", "error_code", "version"],
        search_params={"metric_type": "COSINE", "params": {"ef": 64}},
    )
    hits = []
    for hit in results[0]:
        entity = hit.get("entity", {})
        hits.append(
            {
                "score": float(hit.get("distance", 0.0)),
                "content": entity.get("content", ""),
                "doc_title": entity.get("doc_title", ""),
                "section": entity.get("section", ""),
                "category": entity.get("category", ""),
                "error_code": entity.get("error_code", ""),
                "version": entity.get("version", ""),
            }
        )
    return hits
