"""SWE-bench Verified 的确定性跨仓库分层选择与安全 manifest。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from .dataset import DATASET

SELECTION_SCHEMA_VERSION = 1
SELECTION_STRATEGY = "repo-difficulty-round-robin"
SELECTION_VERSION = "v1"
_KNOWN_DIFFICULTIES = (
    "<15 min fix",
    "15 min - 1 hour",
    "1-4 hours",
    ">4 hours",
)


def normalize_difficulty(value: Any) -> str:
    difficulty = " ".join(str(value or "").strip().lower().split())
    return difficulty if difficulty in _KNOWN_DIFFICULTIES else "unknown"


def _stable_rank(instance_id: str) -> str:
    value = f"{SELECTION_VERSION}:{instance_id}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _repo_queue(instances: list[dict[str, Any]]) -> deque[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for instance in instances:
        buckets[normalize_difficulty(instance.get("difficulty"))].append(instance)
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (_stable_rank(str(item["instance_id"])), item["instance_id"]))

    ordered_buckets = [
        deque(buckets[name]) for name in (*_KNOWN_DIFFICULTIES, "unknown") if buckets.get(name)
    ]
    queue: deque[dict[str, Any]] = deque()
    while ordered_buckets:
        remaining: list[deque[dict[str, Any]]] = []
        for bucket in ordered_buckets:
            queue.append(bucket.popleft())
            if bucket:
                remaining.append(bucket)
        ordered_buckets = remaining
    return queue


def select_instances(instances: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """构造稳定的全局选择前缀，再返回前 ``limit`` 项。"""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_ids: set[str] = set()
    for instance in instances:
        instance_id = str(instance.get("instance_id") or "")
        repo = str(instance.get("repo") or "")
        if not instance_id or not repo:
            raise ValueError("candidate rows require non-empty instance_id and repo")
        if instance_id in seen_ids:
            raise ValueError(f"duplicate instance_id: {instance_id}")
        seen_ids.add(instance_id)
        by_repo[repo].append(instance)

    repo_queues = {repo: _repo_queue(rows) for repo, rows in by_repo.items()}
    selected: list[dict[str, Any]] = []
    while len(selected) < min(limit, len(instances)):
        progressed = False
        for repo in sorted(repo_queues):
            queue = repo_queues[repo]
            if queue:
                selected.append(queue.popleft())
                progressed = True
                if len(selected) == min(limit, len(instances)):
                    break
        if not progressed:
            break
    return selected


def _sha256_lines(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def candidate_fingerprint(instances: list[dict[str, Any]]) -> str:
    """只哈希选择相关的公开元数据，不把题面或隐藏测试复制进 manifest。"""
    rows = [
        json.dumps(
            {
                "instance_id": str(instance["instance_id"]),
                "repo": str(instance["repo"]),
                "difficulty": normalize_difficulty(instance.get("difficulty")),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for instance in instances
    ]
    return _sha256_lines(sorted(rows))


def build_selection_manifest(
    candidates: list[dict[str, Any]], selected: list[dict[str, Any]], requested_limit: int
) -> dict[str, Any]:
    instance_ids = [str(instance["instance_id"]) for instance in selected]
    repo_counts = Counter(str(instance["repo"]) for instance in selected)
    difficulty_counts = Counter(
        normalize_difficulty(instance.get("difficulty")) for instance in selected
    )
    return {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "dataset": DATASET,
        "config": "default",
        "split": "test",
        "selection_strategy": SELECTION_STRATEGY,
        "selection_version": SELECTION_VERSION,
        "candidate_count": len(candidates),
        "candidate_fingerprint": candidate_fingerprint(candidates),
        "requested_limit": requested_limit,
        "selected_count": len(selected),
        "instance_ids": instance_ids,
        "repo_counts": dict(sorted(repo_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "selection_signature": _sha256_lines(instance_ids),
    }


def write_selection_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_selection_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resume_manifest_mismatches(existing: dict[str, Any], current: dict[str, Any]) -> list[str]:
    fields = (
        "schema_version",
        "dataset",
        "config",
        "split",
        "selection_strategy",
        "selection_version",
        "candidate_count",
        "candidate_fingerprint",
        "requested_limit",
        "selected_count",
        "selection_signature",
    )
    return [field for field in fields if existing.get(field) != current.get(field)]
