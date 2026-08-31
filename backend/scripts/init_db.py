# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""建表脚本：创建 MySQL 全部表 + Milvus collection。

用法（在 backend 目录下）：
    python -m scripts.init_db            # 增量建表
    python -m scripts.init_db --recreate # 删表重建 + 重建 Milvus collection
"""

import argparse

from app import models  # noqa: F401  确保所有模型注册到 Base.metadata
from app.db import Base, sync_engine
from app.rag import store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="删表重建")
    args = parser.parse_args()

    if args.recreate:
        print("[init_db] 删除所有表 ...")
        Base.metadata.drop_all(sync_engine)
    print("[init_db] 创建 MySQL 表 ...")
    Base.metadata.create_all(sync_engine)
    tables = sorted(Base.metadata.tables.keys())
    print(f"[init_db] MySQL 表就绪（{len(tables)}）：{tables}")

    print("[init_db] 创建 Milvus collection ...")
    store.ensure_collection(recreate=args.recreate)
    print(f"[init_db] Milvus collection '{store.COLLECTION}' 就绪。")


if __name__ == "__main__":
    main()
