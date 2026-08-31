# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""FastAPI 应用入口。"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, conversations, docs
from app.api import eval as eval_api
from app.api import tickets, traces, workbench
from app.config import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("devsupport")

app = FastAPI(
    title="DevSupport AI",
    description="面向 API 开放平台的多 Agent 智能技术支持系统",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
async def health() -> dict:
    """健康检查。"""
    return {"status": "ok", "env": settings.app_env, "version": app.version}


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(docs.router)
app.include_router(tickets.router)
app.include_router(workbench.router)
app.include_router(traces.router)
app.include_router(eval_api.router)
