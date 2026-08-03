"""控制台的元信息：服务模式、可用工具、供应商、开关目录。

前端「新建运行」表单的字段完全由这里驱动，因此**开关目录是唯一真相源**——
加一个 CLI 开关时只要在这里补一条，表单和「护栏默认开 / 行为默认关」的分组
就会自动跟上，不需要改前端。
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from dm_agent import __version__
from dm_agent.clients import PROVIDER_DEFAULTS
from dm_agent.server.security import get_settings, require_token
from dm_agent.server.settings import ServerSettings
from dm_agent.tools import default_tools

router = APIRouter(prefix="/api", tags=["meta"], dependencies=[Depends(require_token)])

# 各 provider 的 API key 环境变量名。只回报「有没有」，绝不回报值。
PROVIDER_ENV_KEYS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# 开关目录。``category`` 就是项目宪法里的那条分类原则：
#   guardrail —— 基础设施护栏，默认**开**，用户一般不用动
#   behavior  —— 行为 / 算法类，默认**关**，研究者按需逐个打开做 ablation
#   tuning    —— 数值参数，有安全默认值
CAPABILITY_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "flag": "--max-observation-chars",
        "key": "max_observation_chars",
        "kind": "int",
        "default": 8000,
        "category": "guardrail",
        "label": "观察截断",
        "help": "单条工具观察的字符上限；0 表示不截断。",
    },
    {
        "flag": "--context-token-budget",
        "key": "context_token_budget",
        "kind": "int",
        "default": 24000,
        "category": "guardrail",
        "label": "上下文 token 预算",
        "help": "超限时提前触发本地确定性折叠；0 表示只按消息节奏折叠。",
    },
    {
        "flag": "--disable-edit-guard",
        "key": "enable_edit_guard",
        "kind": "bool",
        "default": True,
        "category": "guardrail",
        "label": "read-before-edit 守卫",
        "help": "edit_file 前必须读过目标文件，写后需重读。默认开启。",
    },
    {
        "flag": "--llm-max-retries",
        "key": "llm_max_retries",
        "kind": "int",
        "default": 2,
        "category": "guardrail",
        "label": "LLM 统一重试次数",
        "help": "所有供应商共用一套重试策略。",
    },
    {
        "flag": "--max-steps",
        "key": "max_steps",
        "kind": "int",
        "default": 100,
        "category": "tuning",
        "label": "最大步数",
        "help": "ReAct 循环的硬上限。",
    },
    {
        "flag": "--temperature",
        "key": "temperature",
        "kind": "float",
        "default": 0.7,
        "category": "tuning",
        "label": "采样温度",
        "help": "确定性回归请用 0。",
    },
    {
        "flag": "--enable-adaptive-replanning",
        "key": "enable_adaptive_replanning",
        "kind": "bool",
        "default": False,
        "category": "behavior",
        "label": "Adaptive Replanning",
        "help": "扩展的重规划决策策略与限制。基础重规划本来就一直开着。",
    },
)


@router.get("/meta", summary="服务模式与能力目录")
def read_meta(
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> dict[str, Any]:
    """一次性把前端启动所需的全部静态信息给出去。"""
    return {
        "version": __version__,
        "server": {
            "read_only": settings.read_only,
            "auth_required": settings.auth_required,
            # 工作目录要显示给用户——agent 会在这里读写文件，这是知情同意的一部分。
            # 但**界面上只显示目录名**：把 C:\Users\...\project 这种整条路径怼在侧栏里
            # 既难看又没信息量（本机单用户场景下用户当然知道自己在哪跑）。完整路径留在
            # 这个字段里给 API 消费者与排障用，前端只读 workspace_name。
            "workspace": str(settings.workspace),
            "workspace_name": settings.workspace.name or str(settings.workspace),
            "sessions_dir_name": settings.sessions_dir.name,
        },
        "providers": [
            {
                "name": name,
                "model": defaults.get("model", ""),
                "base_url": defaults.get("base_url", ""),
                "env_key": PROVIDER_ENV_KEYS.get(name, ""),
                # 只回报「配没配」，永不回报 key 本身。
                "api_key_present": bool(os.environ.get(PROVIDER_ENV_KEYS.get(name, ""), "")),
            }
            for name, defaults in PROVIDER_DEFAULTS.items()
        ],
        "capabilities": list(CAPABILITY_CATALOG),
        "tools": [
            {"name": tool.name, "description": tool.description}
            for tool in default_tools(include_mcp=False)
        ],
    }


@router.get("/health", summary="存活探针")
def read_health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
