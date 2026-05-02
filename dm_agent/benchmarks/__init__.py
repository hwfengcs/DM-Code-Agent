"""Coding benchmarks for DM-Code-Agent."""

from .models import BenchmarkRunConfig, BenchmarkTask, BenchmarkVariant, CodingBenchResult
from .runner import BENCH_VARIANTS, DEFAULT_BENCH_VARIANTS, run_benchmark_suite
from .tasks import BUILTIN_CODING_TASKS, get_coding_tasks

__all__ = [
    "BENCH_VARIANTS",
    "BUILTIN_CODING_TASKS",
    "DEFAULT_BENCH_VARIANTS",
    "BenchmarkRunConfig",
    "BenchmarkTask",
    "BenchmarkVariant",
    "CodingBenchResult",
    "get_coding_tasks",
    "run_benchmark_suite",
]
