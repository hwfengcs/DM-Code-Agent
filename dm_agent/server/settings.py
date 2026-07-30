"""Web 控制台的运行时配置与路径安全边界。

这一层刻意不依赖 FastAPI：``ServerSettings`` 是纯 dataclass，路径解析是纯函数，
因此安全相关的断言可以在不起 HTTP 栈的情况下单测。
"""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ServerSettings",
    "SessionPathError",
    "generate_token",
    "is_loopback_host",
    "resolve_session_path",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# 会话文件的唯一合法后缀。限制后缀既是防呆，也让「把 sessions_dir 指到家目录」
# 这类误操作不至于把任意文件读出去。
SESSION_SUFFIX = ".jsonl"


class SessionPathError(ValueError):
    """会话文件名非法、越界或不存在。"""


def is_loopback_host(host: str) -> bool:
    """判断绑定地址是否只对本机可见。

    ``localhost`` 不是合法 IP 字面量，但语义上等价于 loopback，单独放行。
    解析失败的主机名一律**按非 loopback 处理**（fail closed）。
    """
    candidate = host.strip().strip("[]")
    if candidate.lower() in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def generate_token() -> str:
    """生成一次性访问 token（进程内有效，不落盘）。"""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class ServerSettings:
    """一次 ``dm-agent-web`` 进程的全部配置。

    ``token`` 为空表示不校验；构造时会强制「非 loopback 必须有 token」，
    因此不存在「不小心把无鉴权的 agent 执行端点暴露到局域网」这条路径。
    """

    sessions_dir: Path
    workspace: Path = field(default_factory=Path.cwd)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str = ""
    read_only: bool = False
    static_dir: Path | None = None

    def __post_init__(self) -> None:
        # frozen dataclass 里改字段要走 object.__setattr__；这里只做路径规范化。
        object.__setattr__(self, "sessions_dir", Path(self.sessions_dir).resolve())
        object.__setattr__(self, "workspace", Path(self.workspace).resolve())
        if self.static_dir is not None:
            object.__setattr__(self, "static_dir", Path(self.static_dir).resolve())
        if not is_loopback_host(self.host) and not self.token:
            raise ValueError(
                f"绑定到非 loopback 地址（{self.host}）时必须提供 token；"
                "否则同网段任何人都能调用运行端点。"
            )

    @property
    def auth_required(self) -> bool:
        return bool(self.token)

    def public_url(self) -> str:
        """启动时打印给用户的地址，带上 token 以便直接点开。"""
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::", ""} else self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        base = f"http://{host}:{self.port}/"
        return f"{base}?token={self.token}" if self.token else base


def resolve_session_path(settings: ServerSettings, name: str) -> Path:
    """把 API 传来的会话名解析成 ``sessions_dir`` 内的真实路径。

    这是整个 server 层唯一的「外部字符串 → 文件路径」入口，因此四道检查都放在这里：
    后缀必须是 ``.jsonl``、不得是绝对路径、解析后必须仍在 ``sessions_dir`` 内
    （挡 ``../`` 穿越与符号链接逃逸）、且必须是已存在的普通文件。

    Raises:
        SessionPathError: 上述任一条不满足
    """
    if not name or not name.strip():
        raise SessionPathError("会话名不能为空。")
    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive or name.startswith(("/", "\\")):
        raise SessionPathError(f"会话名必须是相对路径：{name}")
    if candidate.suffix.lower() != SESSION_SUFFIX:
        raise SessionPathError(f"只接受 {SESSION_SUFFIX} 会话文件：{name}")

    root = settings.sessions_dir
    # 先 resolve 再比较，符号链接指向目录外时会在这里暴露出来。
    target = (root / candidate).resolve()
    if not _is_within(target, root):
        raise SessionPathError(f"会话名越出了 sessions 目录：{name}")
    if not target.is_file():
        raise SessionPathError(f"会话文件不存在：{name}")
    return target


def relative_session_name(settings: ServerSettings, path: Path) -> str:
    """把真实路径转回 API 用的会话名。

    对外一律只暴露相对名，绝不把开发机的绝对路径写进响应——只读展厅是要公开分享的。
    """
    try:
        return path.resolve().relative_to(settings.sessions_dir).as_posix()
    except ValueError:
        return path.name


def _is_within(target: Path, root: Path) -> bool:
    """``Path.is_relative_to`` 的兼容实现（3.9 起才有，本项目最低 3.10，但保持显式）。"""
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True
