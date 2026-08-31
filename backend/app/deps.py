# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""依赖注入：当前用户、角色校验、租户隔离。"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

# 客户侧角色：只能访问本租户数据
CUSTOMER_ROLES = {"customer_dev", "customer_admin"}
# 内部角色：可进工作台
INTERNAL_ROLES = {"support", "admin"}


@dataclass
class CurrentUser:
    user_id: str
    username: str
    display_name: str
    role: str
    tenant_id: str

    @property
    def is_internal(self) -> bool:
        return self.role in INTERNAL_ROLES


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未提供凭证")
    payload = decode_access_token(cred.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "凭证无效或已过期")
    user_id = payload.get("sub")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        tenant_id=user.tenant_id,
    )


def require_internal(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """要求内部角色（工作台等）。"""
    if not user.is_internal:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要技术支持或管理员权限")
    return user


def assert_tenant_access(user: CurrentUser, target_tenant_id: str) -> None:
    """租户隔离：客户侧角色只能访问本租户数据；内部角色可跨租户。"""
    if user.is_internal:
        return
    if user.tenant_id != target_tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问其它租户数据")
