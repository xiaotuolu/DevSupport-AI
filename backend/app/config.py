# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""应用配置：从环境变量 / .env 读取，集中管理。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ----- LLM / Embedding / Rerank (DashScope, OpenAI 兼容) -----
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model_small: str = "qwen-turbo"
    llm_model_large: str = "qwen-plus"
    embedding_model: str = "text-embedding-v3"
    embedding_dim: int = 1024
    rerank_model: str = "gte-rerank-v2"

    # ----- MySQL -----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_user: str = "devsupport"
    mysql_password: str = "devsupport123"
    mysql_db: str = "devsupport"

    # ----- Milvus -----
    milvus_uri: str = "http://localhost:19531"
    milvus_collection: str = "knowledge_chunk"

    # ----- Redis -----
    redis_url: str = "redis://localhost:6380/0"

    # ----- 认证 -----
    jwt_secret: str = "change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # ----- 业务阈值 -----
    intent_confidence_threshold: float = 0.6   # 意图置信度低于此值触发澄清追问
    rag_score_threshold: float = 0.3           # rerank 分达标即判文档命中
    rag_vec_hit_threshold: float = 0.45        # 向量余弦达标即判文档命中（与上者取其一）
    tool_timeout_seconds: float = 3.0          # 单次工具调用超时
    semantic_cache_sim_threshold: float = 0.95  # 语义缓存命中所需的最低相似度

    # ----- 其它 -----
    app_env: str = "dev"
    log_level: str = "INFO"

    @property
    def mysql_dsn_async(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def mysql_dsn_sync(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
