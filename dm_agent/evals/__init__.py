"""Evaluation harness for DM-Code-Agent."""

from .real_runner import REAL_DEFAULT_VARIANTS, RealEvalConfig, get_real_tasks, run_real_suite
from .runner import DEFAULT_VARIANTS, EvalVariant, run_suite, summarize_results
from .tasks import BUILTIN_TASKS, get_builtin_tasks

__all__ = [
    "BUILTIN_TASKS",
    "DEFAULT_VARIANTS",
    "REAL_DEFAULT_VARIANTS",
    "EvalVariant",
    "RealEvalConfig",
    "get_builtin_tasks",
    "get_real_tasks",
    "run_real_suite",
    "run_suite",
    "summarize_results",
]
