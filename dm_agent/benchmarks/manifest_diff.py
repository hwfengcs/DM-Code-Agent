"""Offline diff for benchmark report manifests.

The command compares existing benchmark JSON files only. It never runs benchmarks,
models, verifiers, or network calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class ManifestDiff:
    """Structured comparison of two benchmark manifests."""

    compatible: bool
    suite_signature_match: bool
    suite_match: bool
    variant_names_match: bool
    missing_in_right: List[str]
    missing_in_left: List[str]
    changed_fingerprints: List[str]
    left_signature: str
    right_signature: str
    left_suite: str
    right_suite: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compatible": self.compatible,
            "suite_signature_match": self.suite_signature_match,
            "suite_match": self.suite_match,
            "variant_names_match": self.variant_names_match,
            "missing_in_right": self.missing_in_right,
            "missing_in_left": self.missing_in_left,
            "changed_fingerprints": self.changed_fingerprints,
            "left_signature": self.left_signature,
            "right_signature": self.right_signature,
            "left_suite": self.left_suite,
            "right_suite": self.right_suite,
        }


def diff_report_manifests(
    left_report: Dict[str, Any], right_report: Dict[str, Any]
) -> ManifestDiff:
    """Compare the manifest blocks of two benchmark reports."""

    left = _manifest(left_report)
    right = _manifest(right_report)
    left_fingerprints = _task_fingerprints(left)
    right_fingerprints = _task_fingerprints(right)
    left_tasks = set(left_fingerprints)
    right_tasks = set(right_fingerprints)
    shared_tasks = left_tasks & right_tasks
    changed = sorted(
        task_id
        for task_id in shared_tasks
        if left_fingerprints.get(task_id) != right_fingerprints.get(task_id)
    )

    suite_signature_match = _signature(left) == _signature(right) and bool(_signature(left))
    suite_match = str(left.get("suite", "")) == str(right.get("suite", ""))
    variant_names_match = _variant_names(left) == _variant_names(right)
    missing_in_right = sorted(left_tasks - right_tasks)
    missing_in_left = sorted(right_tasks - left_tasks)
    compatible = (
        suite_signature_match
        and suite_match
        and variant_names_match
        and not missing_in_right
        and not missing_in_left
        and not changed
    )
    return ManifestDiff(
        compatible=compatible,
        suite_signature_match=suite_signature_match,
        suite_match=suite_match,
        variant_names_match=variant_names_match,
        missing_in_right=missing_in_right,
        missing_in_left=missing_in_left,
        changed_fingerprints=changed,
        left_signature=_signature(left),
        right_signature=_signature(right),
        left_suite=str(left.get("suite", "")),
        right_suite=str(right.get("suite", "")),
    )


def render_markdown(
    diff: ManifestDiff, *, left_label: str = "left", right_label: str = "right"
) -> str:
    """Render a human-readable manifest diff."""

    status = "compatible" if diff.compatible else "different"
    lines = [
        "# Benchmark Manifest Diff",
        "",
        f"- Status: `{status}`",
        f"- Left: `{left_label}`",
        f"- Right: `{right_label}`",
        f"- Suite: `{diff.left_suite}` vs `{diff.right_suite}`",
        f"- Suite signature: `{diff.left_signature or '<missing>'}` vs "
        f"`{diff.right_signature or '<missing>'}`",
        f"- Suite signature match: `{diff.suite_signature_match}`",
        f"- Variant names match: `{diff.variant_names_match}`",
        "",
        "## Task Fingerprints",
        "",
    ]
    if diff.compatible:
        lines.append("Task fingerprints and suite signatures match.")
    else:
        lines.extend(
            [
                f"- Missing in right: `{', '.join(diff.missing_in_right) or 'none'}`",
                f"- Missing in left: `{', '.join(diff.missing_in_left) or 'none'}`",
                f"- Changed fingerprints: `{', '.join(diff.changed_fingerprints) or 'none'}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def load_json_report(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object report")
    return payload


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare benchmark report manifests offline.")
    parser.add_argument("left", type=Path, help="Baseline benchmark JSON report.")
    parser.add_argument("right", type=Path, help="Comparison benchmark JSON report.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of Markdown.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        left = load_json_report(args.left)
        right = load_json_report(args.right)
        diff = diff_report_manifests(left, right)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Failed to diff benchmark manifests: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(diff.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(diff, left_label=str(args.left), right_label=str(args.right)))
    return 0 if diff.compatible else 1


def _manifest(report: Dict[str, Any]) -> Dict[str, Any]:
    manifest = report.get("manifest") or {}
    return manifest if isinstance(manifest, dict) else {}


def _task_fingerprints(manifest: Dict[str, Any]) -> Dict[str, str]:
    fingerprints = manifest.get("task_fingerprints") or {}
    if not isinstance(fingerprints, dict):
        return {}
    return {str(task_id): str(fingerprint) for task_id, fingerprint in fingerprints.items()}


def _variant_names(manifest: Dict[str, Any]) -> List[str]:
    return sorted(str(name) for name in manifest.get("variant_names") or [])


def _signature(manifest: Dict[str, Any]) -> str:
    return str(manifest.get("suite_signature") or "")


if __name__ == "__main__":
    raise SystemExit(main())
