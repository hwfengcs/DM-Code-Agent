"""运行时配置：Config 数据类、config.json 读写与高级开关解析。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dm_agent.paths import (
    atomic_write_json,
    resolve_config_read_path,
    resolve_config_write_path,
    user_env_path,
)

from .ui import UI

# 缺 key 时告诉用户去哪儿领。纯展示信息，刻意不放进 clients 层的 PROVIDER_DEFAULTS——
# 那是构造客户端用的数据，不该混入面向人的文案。
PROVIDER_CONSOLE_URLS = {
    "deepseek": "https://platform.deepseek.com/api_keys",
    "openai": "https://platform.openai.com/api-keys",
    "claude": "https://console.anthropic.com/settings/keys",
    "gemini": "https://aistudio.google.com/apikey",
}


@dataclass
class Config:
    """运行时配置"""

    api_key: str
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    max_steps: int = 100
    temperature: float = 0.7
    show_steps: bool = False
    max_observation_chars: int = 8000
    context_token_budget: int = 24000
    enable_edit_guard: bool = True
    llm_max_retries: int = 2
    enable_adaptive_replanning: bool = False
    max_replans: int = -1


def load_config_from_file() -> dict[str, Any]:
    """读取配置：``./config.json`` 优先，其次 ``~/.dm_agent/config.json``。

    两者都不存在时返回空字典，由调用方用硬编码默认值。文件损坏时告警并降级，
    绝不让一个坏配置挡住整个 CLI。
    """
    path = resolve_config_read_path()
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            return data
    except Exception as e:
        UI.status("warn", "配置文件加载失败，使用默认设置", f"{path}：{e}")
    return {}


def save_config_to_file(config: Config) -> None:
    """保存配置，写回**读到的那一个**文件；都不存在时落用户级。

    用原子写：临时文件 → fsync → ``os.replace``，避免写到一半崩掉留下半个 JSON
    （下次启动就会走上面那条「加载失败」分支，用户的设置静默丢失）。
    """
    path = resolve_config_write_path()
    try:
        config_data = {
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "max_steps": config.max_steps,
            "temperature": config.temperature,
            "show_steps": config.show_steps,
            "max_observation_chars": config.max_observation_chars,
            "context_token_budget": config.context_token_budget,
            "enable_edit_guard": config.enable_edit_guard,
            "llm_max_retries": config.llm_max_retries,
            "enable_adaptive_replanning": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
        }
        atomic_write_json(path, config_data)
        UI.status("ok", "配置已保存", str(path))
    except Exception as e:
        UI.status("error", "配置保存失败", str(e))


def format_missing_api_key_help(provider: str) -> str:
    """缺 key 时的多行提示。

    给的是**算出来的绝对路径**而不是「请在 .env 中配置」——全局安装后用户的
    ``.env`` 该放哪不再是显然的，泛泛一句提示等于没说。
    """
    env_var = f"{provider.upper()}_API_KEY"
    setter = f"set {env_var}=sk-xxx" if os.name == "nt" else f"export {env_var}=sk-xxx"
    lines = [
        "三种配法（任选其一）：",
        f"  1. 环境变量   {setter}",
        f"  2. 用户级配置 {user_env_path()}",
        f"                写入 {env_var}=sk-xxx",
        f"  3. 项目级      {Path.cwd() / '.env'}",
    ]
    console_url = PROVIDER_CONSOLE_URLS.get(provider.casefold())
    if console_url:
        lines.append("")
        lines.append(f"获取 key: {console_url}")
    return "\n".join(lines)


def get_api_key_for_provider(provider: str) -> str | None:
    """根据提供商获取对应的 API 密钥"""
    provider_env_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "CLAUDE_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_var = provider_env_map.get(provider.lower())
    return os.getenv(env_var) if env_var else None


def resolve_advanced_features(config: Config) -> dict[str, bool]:
    """Return effective advanced feature switches for one agent run."""
    return {
        "adaptive_replanning": config.enable_adaptive_replanning,
    }


def format_advanced_feature_status(config: Config) -> str:
    """Compact human-readable summary of advanced feature switches."""
    advanced = resolve_advanced_features(config)
    enabled = [
        label
        for key, label in [
            ("adaptive_replanning", "adaptive-replan"),
        ]
        if advanced[key]
    ]
    return ", ".join(enabled) if enabled else "off"
