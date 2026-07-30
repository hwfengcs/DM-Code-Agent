"""FastAPI 应用工厂。

``dm_agent.server`` 是与 ``dm_agent.cli`` 同级的另一个最外层装配者：它可以依赖任何
下层，但**不得 import cli**——需要真正跑 agent 时它 spawn 一个 CLI 子进程，
而不是把 CLI 当库用。这条由 ``tests/test_server_layering.py`` 断言。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from dm_agent import __version__

from .routes import meta, sessions
from .settings import ServerSettings

__all__ = ["create_app", "default_static_dir"]

# Vite 开发服务器的默认来源。只放行 loopback：真正的鉴权靠 token，
# CORS 在这里只是让 `npm run dev` 能直连后端，不承担安全职责。
_DEV_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


def default_static_dir() -> Path | None:
    """返回随包分发的前端产物目录；未构建时返回 None。"""
    candidate = Path(__file__).resolve().parent / "static"
    return candidate if (candidate / "index.html").is_file() else None


class SPAStaticFiles(StaticFiles):
    """带 history-fallback 的静态文件服务。

    前端用的是客户端路由，``/sessions/foo`` 这种深链在磁盘上并不存在对应文件。
    原版 ``StaticFiles`` 会返回 404，这里改成回落到 ``index.html``，由前端自己解析路径。
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


def create_app(settings: ServerSettings) -> FastAPI:
    """按配置装配应用。

    路由顺序有意义：API 路由先注册，静态文件挂在 ``/`` 兜底。Starlette 按注册顺序
    匹配，所以根挂载不会吃掉 ``/api/*``。
    """
    app = FastAPI(
        title="DM-Code-Agent Web Console",
        version=__version__,
        description=(
            "本地优先、可审计的 Code Agent 控制台。只读端点在 --read-only 下依然全部可用。"
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_DEV_ORIGIN_REGEX,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(meta.router)
    app.include_router(sessions.router)

    static_dir = settings.static_dir or default_static_dir()
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
    else:
        # 前端还没构建（或有意只跑 API）时给一个自解释的响应，而不是 404。
        @app.get("/", include_in_schema=False)
        def _no_frontend() -> JSONResponse:
            return JSONResponse(_frontend_missing_payload())

    return app


def _frontend_missing_payload() -> dict[str, Any]:
    return {
        "detail": "前端产物未构建，API 仍然可用。",
        "build": "cd web && npm install && npm run build",
        "api_docs": "/api/docs",
        "version": __version__,
    }
