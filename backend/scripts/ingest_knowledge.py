# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""知识库 ingest 脚本：把 data/knowledge/*.md 切片向量化写入 Milvus。

用法（backend 目录下）：python -m scripts.ingest_knowledge
"""

import asyncio

from app.rag.ingest import ingest_all


def main() -> None:
    stats = asyncio.run(ingest_all(recreate=True))
    print(f"[ingest] 完成：文档 {stats['documents']} 篇，切片 {stats['chunks']} 个。")


if __name__ == "__main__":
    main()
