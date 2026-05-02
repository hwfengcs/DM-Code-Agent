"""Benchmark suites for DM-Code-Agent."""

from .models import BenchmarkRunConfig, BenchmarkTask, BenchmarkVariant, CodingBenchResult
from .runner import BENCH_VARIANTS, DEFAULT_BENCH_VARIANTS, run_benchmark_suite
from .tasks import (
    BENCHMARK_SUITES,
    BUILTIN_CODING_TASKS,
    BUILTIN_MAINTENANCE_TASKS,
    get_benchmark_tasks,
    get_coding_tasks,
    get_maintenance_tasks,
)

__all__ = [
    "BENCH_VARIANTS",
    "BENCHMARK_SUITES",
    "BUILTIN_CODING_TASKS",
    "BUILTIN_MAINTENANCE_TASKS",
    "DEFAULT_BENCH_VARIANTS",
    "BenchmarkRunConfig",
    "BenchmarkTask",
    "BenchmarkVariant",
    "CodingBenchResult",
    "get_benchmark_tasks",
    "get_coding_tasks",
    "get_maintenance_tasks",
    "run_benchmark_suite",
]
