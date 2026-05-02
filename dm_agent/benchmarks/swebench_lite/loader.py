"""Loader for the SWE-bench Lite dataset.

The default path uses the HuggingFace `datasets` library. Because that pulls
in pyarrow + a multi-megabyte cache, it lives in the optional ``[swebench]``
extra. Tests use :func:`load_instances_from_jsonl` to avoid the dependency.

Local cache layout::

    ~/.cache/dm-agent/swebench_lite/
        princeton_nlp_swe_bench_lite_test.jsonl   # snapshot of the 300 instances
        subset_50_seed42.json                     # deterministic 50-instance subset

We materialize the dataset to JSONL on first load so subsequent runs do not
re-hit HuggingFace, and so a frozen subset can be checked into the repository
without redistributing the source data.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import SWEBenchInstance

DEFAULT_DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
DEFAULT_SPLIT = "test"
SUBSET_50_SEED = 42
SUBSET_50_SIZE = 50


def _cache_dir() -> Path:
    root = os.environ.get("DM_AGENT_CACHE_DIR")
    if root:
        return Path(root) / "swebench_lite"
    return Path.home() / ".cache" / "dm-agent" / "swebench_lite"


def _snapshot_path(split: str = DEFAULT_SPLIT) -> Path:
    return _cache_dir() / f"princeton_nlp_swe_bench_lite_{split}.jsonl"


def _row_to_instance(row: Dict[str, Any]) -> SWEBenchInstance:
    """Convert a raw HuggingFace row to a SWEBenchInstance.

    Different exports format the FAIL_TO_PASS / PASS_TO_PASS fields as either
    JSON strings or Python lists. Normalize here so callers always see lists.
    """

    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
            return [item.strip() for item in value.split("\n") if item.strip()]
        return [str(value)]

    return SWEBenchInstance(
        instance_id=str(row["instance_id"]),
        repo=str(row["repo"]),
        version=str(row.get("version", "")),
        base_commit=str(row["base_commit"]),
        environment_setup_commit=str(row.get("environment_setup_commit", row["base_commit"])),
        problem_statement=str(row.get("problem_statement", "")),
        hints_text=str(row.get("hints_text", "") or ""),
        created_at=str(row.get("created_at", "") or ""),
        patch=str(row.get("patch", "") or ""),
        test_patch=str(row.get("test_patch", "") or ""),
        fail_to_pass=_as_list(row.get("FAIL_TO_PASS")),
        pass_to_pass=_as_list(row.get("PASS_TO_PASS")),
    )


def _instance_to_row(instance: SWEBenchInstance) -> Dict[str, Any]:
    return {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "version": instance.version,
        "base_commit": instance.base_commit,
        "environment_setup_commit": instance.environment_setup_commit,
        "problem_statement": instance.problem_statement,
        "hints_text": instance.hints_text,
        "created_at": instance.created_at,
        "patch": instance.patch,
        "test_patch": instance.test_patch,
        "FAIL_TO_PASS": list(instance.fail_to_pass),
        "PASS_TO_PASS": list(instance.pass_to_pass),
    }


def load_instances_from_jsonl(path: str | Path) -> List[SWEBenchInstance]:
    """Load instances from a previously snapshotted JSONL file.

    The JSONL format matches the HuggingFace export schema and is what
    :func:`snapshot_to_jsonl` writes. Used by tests and offline runs.
    """
    instances: List[SWEBenchInstance] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            instances.append(_row_to_instance(row))
    return instances


def snapshot_to_jsonl(instances: Iterable[SWEBenchInstance], path: str | Path) -> Path:
    """Write instances back out as JSONL for later offline reload."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for instance in instances:
            handle.write(json.dumps(_instance_to_row(instance), ensure_ascii=False))
            handle.write("\n")
    return path


def _load_via_datasets(split: str) -> List[SWEBenchInstance]:
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:  # pragma: no cover - guarded by extra
        raise RuntimeError(
            "The 'datasets' library is required to download SWE-bench Lite. "
            'Install with: pip install "dm-code-agent[swebench]"'
        ) from exc

    dataset = load_dataset(DEFAULT_DATASET_NAME, split=split)
    return [_row_to_instance(dict(row)) for row in dataset]


def load_instances(
    *,
    split: str = DEFAULT_SPLIT,
    instance_ids: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    refresh: bool = False,
    snapshot_path: Optional[str | Path] = None,
) -> List[SWEBenchInstance]:
    """Load SWE-bench Lite instances, preferring a local snapshot when available.

    Args:
        split: HuggingFace dataset split. Lite only has ``"test"``.
        instance_ids: If provided, return only matching instances (preserves order).
        limit: If provided, cap the number of returned instances after filtering.
        refresh: If True, ignore the local snapshot and re-download from HuggingFace.
        snapshot_path: Override the on-disk cache location.

    Returns:
        A list of :class:`SWEBenchInstance` objects.

    Raises:
        RuntimeError: If neither a local snapshot nor the ``datasets`` library
            is available.
    """
    cache_path = Path(snapshot_path) if snapshot_path else _snapshot_path(split)

    instances: Optional[List[SWEBenchInstance]] = None
    if cache_path.exists() and not refresh:
        instances = load_instances_from_jsonl(cache_path)
    if instances is None:
        instances = _load_via_datasets(split)
        snapshot_to_jsonl(instances, cache_path)

    if instance_ids is not None:
        wanted = list(instance_ids)
        order = {iid: i for i, iid in enumerate(wanted)}
        wanted_set = set(wanted)
        instances = sorted(
            (inst for inst in instances if inst.instance_id in wanted_set),
            key=lambda inst: order[inst.instance_id],
        )

    if limit is not None:
        instances = instances[:limit]

    return instances


def fixed_subset_50(
    *,
    instances: Optional[Sequence[SWEBenchInstance]] = None,
    seed: int = SUBSET_50_SEED,
    size: int = SUBSET_50_SIZE,
    max_per_repo: int = 5,
) -> List[SWEBenchInstance]:
    """Return a deterministic 50-instance subset of SWE-bench Lite.

    Sampling strategy:
      1. Group instances by ``repo``.
      2. From each repo, take up to ``max_per_repo`` instances; seed-shuffled.
      3. Round-robin across repos until we hit ``size``, preserving repo diversity.
      4. Stable secondary sort by ``instance_id`` so identical seeds always
         produce identical orderings independent of dictionary insertion order.

    Args:
        instances: If provided, sample from this list. Otherwise call
            :func:`load_instances` to fetch the full Lite test split.
        seed: Random seed; recorded in benchmark reports for reproducibility.
        size: Number of instances to return.
        max_per_repo: Cap to keep one repo from dominating the subset.

    Returns:
        Up to ``size`` instances. May be smaller if the source has fewer.
    """
    pool = list(instances) if instances is not None else load_instances()
    by_repo: Dict[str, List[SWEBenchInstance]] = defaultdict(list)
    for inst in pool:
        by_repo[inst.repo].append(inst)

    rng = random.Random(seed)
    repo_buckets: Dict[str, List[SWEBenchInstance]] = {}
    for repo, items in by_repo.items():
        items_sorted = sorted(items, key=lambda inst: inst.instance_id)
        rng.shuffle(items_sorted)
        repo_buckets[repo] = items_sorted[:max_per_repo]

    repos = sorted(repo_buckets.keys())
    rng.shuffle(repos)

    selected: List[SWEBenchInstance] = []
    cursor = {repo: 0 for repo in repos}
    while len(selected) < size:
        progress = False
        for repo in repos:
            if len(selected) >= size:
                break
            idx = cursor[repo]
            if idx < len(repo_buckets[repo]):
                selected.append(repo_buckets[repo][idx])
                cursor[repo] = idx + 1
                progress = True
        if not progress:
            break

    return selected


def subset_signature(instances: Sequence[SWEBenchInstance]) -> str:
    """Return a short hash of an instance ID list, for inclusion in reports."""
    payload = "\n".join(inst.instance_id for inst in instances).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]
