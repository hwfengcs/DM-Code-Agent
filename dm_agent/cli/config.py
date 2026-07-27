"""运行时配置：Config 数据类、config.json 读写与高级开关解析。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ui import UI

# 配置文件与历史上的顶级 main.py 同目录（仓库根 / 安装根），搬进包内后显式回溯两级保持一致。
CONFIG_FILE = str(Path(__file__).resolve().parents[2] / "config.json")


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
    enable_reflexion: bool = False
    max_trials: int = 3
    enable_critic: bool = False
    enable_adaptive_replanning: bool = False
    max_replans: int = -1
    enable_repeated_failure_policy_experiment: bool = False
    enable_evolution: bool = False
    enable_memory_hygiene: bool = False
    enable_llm_compression: bool = False
    enable_circuit_breaker: bool = False
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown: int = 5
    reflexion_memory_file: str = ""


def load_config_from_file() -> dict[str, Any]:
    """从配置文件加载设置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            UI.status("warn", "配置文件加载失败，使用默认设置", str(e))
    return {}


def save_config_to_file(config: Config) -> None:
    """保存配置到文件"""
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
            "enable_reflexion": config.enable_reflexion,
            "max_trials": config.max_trials,
            "enable_critic": config.enable_critic,
            "enable_adaptive_replanning": config.enable_adaptive_replanning,
            "max_replans": config.max_replans,
            "enable_repeated_failure_policy_experiment": (
                config.enable_repeated_failure_policy_experiment
            ),
            "enable_evolution": config.enable_evolution,
            "enable_memory_hygiene": config.enable_memory_hygiene,
            "enable_llm_compression": config.enable_llm_compression,
            "enable_circuit_breaker": config.enable_circuit_breaker,
            "circuit_breaker_threshold": config.circuit_breaker_threshold,
            "circuit_breaker_cooldown": config.circuit_breaker_cooldown,
            "reflexion_memory_file": config.reflexion_memory_file,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        UI.status("ok", "配置已保存")
    except Exception as e:
        UI.status("error", "配置保存失败", str(e))


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
    adaptive_replanning = config.enable_adaptive_replanning or config.enable_evolution
    repeated_failure_policy = (
        config.enable_repeated_failure_policy_experiment or config.enable_evolution
    )
    return {
        "reflexion": config.enable_reflexion,
        "critic": config.enable_critic,
        "adaptive_replanning": adaptive_replanning,
        "repeated_failure_policy_experiment": repeated_failure_policy,
        "evolution": config.enable_evolution,
        "memory_hygiene": config.enable_memory_hygiene,
        "llm_compression": config.enable_llm_compression,
        "circuit_breaker": config.enable_circuit_breaker,
    }


def format_advanced_feature_status(config: Config) -> str:
    """Compact human-readable summary of advanced feature switches."""
    advanced = resolve_advanced_features(config)
    enabled = [
        label
        for key, label in [
            ("reflexion", "reflexion"),
            ("critic", "critic"),
            ("adaptive_replanning", "adaptive-replan"),
            ("repeated_failure_policy_experiment", "loop-break"),
            ("evolution", "evolution"),
            ("memory_hygiene", "memory-hygiene"),
            ("llm_compression", "llm-compression"),
            ("circuit_breaker", "circuit-breaker"),
        ]
        if advanced[key]
    ]
    return ", ".join(enabled) if enabled else "off"
