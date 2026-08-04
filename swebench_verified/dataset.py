"""SWE-bench Verified 数据集拉取。

不依赖 ``datasets`` 库：devlog 33 删掉 ``[swebench]`` extra 时，光 ``datasets``
就拖来 26 个传递依赖、让 uv.lock 多 1393 行。HuggingFace 的 datasets-server
提供同一份数据的 JSON 视图，用标准库 urllib 就能取，主项目因此一个新依赖都不加。

拉下来的实例缓存成 JSONL，后续运行不再打网络。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATASET = "princeton-nlp/SWE-bench_Verified"
_ROWS_API = "https://datasets-server.huggingface.co/rows"
_PAGE = 100  # datasets-server 单次返回上限

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


def _fetch_page(offset: int, length: int) -> list[dict[str, Any]]:
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
    if "rows" not in payload:
        raise RuntimeError(f"datasets-server 未返回 rows：{json.dumps(payload)[:400]}")
    return [row["row"] for row in payload["rows"]]


def fetch_instances(limit: int, *, cache_path: Path) -> list[dict[str, Any]]:
    """取前 ``limit`` 条实例（数据集自带顺序，确定性可复现）。

    数据集按 instance_id 字典序排列，取前 N 条等价于一个稳定子集——换机器、
    换时间跑同一个 ``--limit`` 拿到的是同一批题，报告之间才可比。
    """
    if cache_path.exists():
        cached = [json.loads(line) for line in cache_path.read_text(encoding="utf-8").splitlines()]
        if len(cached) >= limit:
            return cached[:limit]

    rows: list[dict[str, Any]] = []
    while len(rows) < limit:
        page = _fetch_page(len(rows), min(_PAGE, limit - len(rows)))
        if not page:
            break
        rows.extend(page)

    instances = [{field: row.get(field) for field in _FIELDS} for row in rows[:limit]]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in instances) + "\n",
        encoding="utf-8",
    )
    return instances


def image_name(instance_id: str) -> str:
    """实例对应的官方评测镜像。

    命名规则取自 swebench 4.1.0 的 ``harness/test_spec/test_spec.py``：
    仓库 slug 里的 ``__`` 在镜像名中写作 ``_1776_``。
    """
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"
