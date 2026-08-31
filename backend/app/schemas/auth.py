# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""认证相关 DTO。"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    tenant_id: str
    tenant_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
