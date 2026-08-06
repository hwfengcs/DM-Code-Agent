"""SWE-bench Verified 数据集拉取。

不依赖 ``datasets`` 库：devlog 33 删掉 ``[swebench]`` extra 时，光 ``datasets``
就拖来 26 个传递依赖、让 uv.lock 多 1393 行。HuggingFace 的 datasets-server
提供同一份数据的 JSON 视图，用标准库 urllib 就能取，主项目因此一个新依赖都不加。

拉下来的实例缓存成 JSONL，后续运行不再打网络。
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATASET = "princeton-nlp/SWE-bench_Verified"
_ROWS_API = "https://datasets-server.huggingface.co/rows"
_PAGE = 100  # datasets-server 单次返回上限
_CACHE_SCHEMA_VERSION = 1

# 一条实例真正需要的字段。problem_statement 是喂给 agent 的题面；
# FAIL_TO_PASS / PASS_TO_PASS 只有官方 harness 用得到，我们原样透传不解读。
_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "version",
    "difficulty",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
)


def _fetch_page(offset: int, length: int) -> tuple[list[dict[str, Any]], int]:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": "default",
            "split": "test",
            "offset": offset,
            "length": length,
        }
    )
    with urllib.request.urlopen(f"{_ROWS_API}?{query}", timeout=120) as response:
        payload = json.load(response)
    if "rows" not in payload or not isinstance(payload.get("num_rows_total"), int):
        raise RuntimeError(f"datasets-server 未返回 rows：{json.dumps(payload)[:400]}")
    return [row["row"] for row in payload["rows"]], payload["num_rows_total"]


def _cache_metadata_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def _instances_fingerprint(instances: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        json.dumps(instance, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for instance in instances
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_complete_cache(cache_path: Path) -> list[dict[str, Any]] | None:
    metadata_path = _cache_metadata_path(cache_path)
    if not cache_path.exists() or not metadata_path.exists():
        return None
    try:
        instances = [
            json.loads(line)
            for line in cache_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "dataset": DATASET,
        "config": "default",
        "split": "test",
        "complete": True,
        "row_count": len(instances),
        "fingerprint": _instances_fingerprint(instances),
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        return None
    return instances


def _write_complete_cache(cache_path: Path, instances: list[dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_tmp = cache_path.with_name(f"{cache_path.name}.tmp")
    metadata_path = _cache_metadata_path(cache_path)
    metadata_tmp = metadata_path.with_name(f"{metadata_path.name}.tmp")
    cache_tmp.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in instances) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "dataset": DATASET,
        "config": "default",
        "split": "test",
        "complete": True,
        "row_count": len(instances),
        "fingerprint": _instances_fingerprint(instances),
    }
    metadata_tmp.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cache_tmp.replace(cache_path)
    metadata_tmp.replace(metadata_path)


def fetch_instances(*, cache_path: Path) -> list[dict[str, Any]]:
    """读取完整 Verified test 候选集；旧 partial cache 会被重新拉取。

    JSONL 旁的 metadata 明确记录完整性、行数与指纹。没有 metadata 的旧缓存无法证明
    自己覆盖了完整 split，因此不能用于跨仓库抽样。
    """
    cached = _read_complete_cache(cache_path)
    if cached is not None:
        return cached

    rows: list[dict[str, Any]] = []
    expected_total: int | None = None
    while expected_total is None or len(rows) < expected_total:
        page, total = _fetch_page(len(rows), _PAGE)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise RuntimeError(f"datasets-server 分页期间总行数变化：{expected_total} -> {total}")
        if not page:
            if expected_total == 0:
                break
            raise RuntimeError(f"datasets-server 在 {len(rows)}/{expected_total} 行处提前返回空页")
        rows.extend(page)
    if len(rows) != expected_total:
        raise RuntimeError(f"datasets-server 返回 {len(rows)} 行，预期 {expected_total} 行")

    instances = [{field: row.get(field) for field in _FIELDS} for row in rows]
    instance_ids = [instance["instance_id"] for instance in instances]
    if len(set(instance_ids)) != len(instance_ids):
        raise RuntimeError("datasets-server 返回了重复 instance_id")
    _write_complete_cache(cache_path, instances)
    return instances


def image_name(instance_id: str) -> str:
    """实例对应的官方评测镜像。

    命名规则取自 swebench 4.1.0 的 ``harness/test_spec/test_spec.py``：
    仓库 slug 里的 ``__`` 在镜像名中写作 ``_1776_``。
    """
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"
