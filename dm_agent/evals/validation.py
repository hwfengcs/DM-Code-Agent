"""Input contracts shared by evaluation runners and offline report readers."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

T = TypeVar("T")


def select_named(
    items: Sequence[T], names: Iterable[str] | None, key: Callable[[T], str], label: str
) -> list[T]:
    selected = list(items)
    if names is not None:
        requested = set(names)
        unknown = requested - {key(item) for item in selected}
        if unknown:
            raise ValueError(f"unknown {label}: {', '.join(sorted(unknown))}")
        selected = [item for item in selected if key(item) in requested]
    if not selected:
        raise ValueError(f"no {label} selected")
    return selected


def positive_int(name: str, value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be at least 1")


def nonnegative_number(name: str, value: Any) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite non-negative number")


def report_results(
    report: dict[str, Any], *, require_identity: bool = True
) -> list[dict[str, Any]]:
    """Require typed outcomes; optional legacy declarations must agree when present."""
    results = report.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("results must be a non-empty list")
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise ValueError(f"results[{index}] must be an object")
        for key in ("task_id", "variant"):
            if not require_identity and key not in result:
                continue
            if not isinstance(result.get(key), str) or not result[key]:
                raise ValueError(f"results[{index}].{key} must be a non-empty string")
        if type(result.get("success")) is not bool:
            raise ValueError(f"results[{index}].success must be a boolean")
        if "estimated_tokens" in result:
            value = result["estimated_tokens"]
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"results[{index}].estimated_tokens must be a non-negative integer"
                )
        if "estimated_cost_usd" in result:
            nonnegative_number(f"results[{index}].estimated_cost_usd", result["estimated_cost_usd"])

    if not require_identity and any(
        "task_id" not in item or "variant" not in item for item in results
    ):
        if any(key in report for key in ("repeat", "tasks", "variants")):
            raise ValueError("declared experiments require task_id and variant in every result")
        return results
    counts = Counter((item["task_id"], item["variant"]) for item in results)
    if "repeat" in report:
        positive_int("repeat", report["repeat"])
        if any(count != report["repeat"] for count in counts.values()):
            raise ValueError("result counts do not match declared repeat")
    declarations: dict[str, set[str]] = {}
    for field, key, result_key in (
        ("tasks", "task_id", "task_id"),
        ("variants", "name", "variant"),
    ):
        if field not in report:
            continue
        entries = report[field]
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{field} must be a non-empty list")
        names = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get(key), str) or not entry[key]:
                raise ValueError(f"{field} entries require a non-empty {key}")
            names.append(entry[key])
        if len(set(names)) != len(names) or set(names) != {item[result_key] for item in results}:
            raise ValueError(f"declared {field} do not match results")
        declarations[field] = set(names)
    if "tasks" in declarations and "variants" in declarations:
        expected = {
            (task, variant)
            for task in declarations["tasks"]
            for variant in declarations["variants"]
        }
        if set(counts) != expected:
            raise ValueError("results do not cover every declared task/variant pair")
    return results
