"""鉴权与写权限守卫。

两条规则，都在这里落地：

1. **token**：``settings.token`` 非空时，所有 ``/api`` 请求必须带上。优先读
   ``Authorization: Bearer``，其次读 ``?token=``——浏览器的 ``EventSource``
   不能自定义请求头，SSE 端点只能走查询参数。
2. **只读模式**：``--read-only`` 下任何会改变磁盘状态的端点（发起运行、分叉会话）
   一律 403。这是公开展厅的默认姿势。
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import ServerSettings

__all__ = ["get_settings", "require_token", "require_writable"]

# auto_error=False：没有 Authorization 头时返回 None 而不是直接 403，
# 好让下面的处理器回退去看查询参数里的 token。
_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> ServerSettings:
    """从应用状态取配置。``create_app`` 在构造时把它挂上去。"""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, ServerSettings):  # pragma: no cover - 装配错误才会发生
        raise RuntimeError("应用未正确装配 ServerSettings。")
    return settings


def require_token(
    settings: Annotated[ServerSettings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    token: Annotated[str | None, Query(description="EventSource 无法设置请求头时的回退")] = None,
) -> None:
    """校验访问 token；``settings.token`` 为空时直接放行。"""
    if not settings.auth_required:
        return
    presented = credentials.credentials if credentials is not None else (token or "")
    # compare_digest 做常数时间比较，避免按字节提前返回泄漏 token 前缀。
    if not presented or not secrets.compare_digest(presented, settings.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或错误的访问 token。",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_writable(settings: Annotated[ServerSettings, Depends(get_settings)]) -> None:
    """只读模式下拦下所有写操作。"""
    if settings.read_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="服务以 --read-only 启动，该操作不可用。",
        )
