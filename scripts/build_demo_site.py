"""Build the public exhibit from fresh, public fixtures; keep raw traces outside it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from dm_agent import __version__
from dm_agent.demo import run_demo
from dm_agent.tracing.export_html import export_session_report
from dm_agent.tracing.session import load_session_entries

ROOT = Path(__file__).resolve().parents[1]


def _empty_directory(path: Path) -> Path:
    if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise ValueError(f"Choose a new or empty directory: {path}")
    return path.resolve()


def build_site(output: Path, demo_output: Path) -> dict[str, Any]:
    """Only derived reports and known public fixture files enter the published directory."""
    output, demo_output = _empty_directory(output), _empty_directory(demo_output)
    if output == demo_output or output in demo_output.parents or demo_output in output.parents:
        raise ValueError("The exhibit and raw demo directories must be separate siblings.")
    manifest = run_demo(demo_output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js", "mark.svg"):
        shutil.copyfile(ROOT / "site" / name, output / name)
    cases = output / "cases"
    cases.mkdir()
    # 已审阅的单文件报告；不复制原始 trace、模型用量或本机工作区。
    shutil.copyfile(
        ROOT / "docs" / "case-studies" / "failure-classification" / "report.html",
        cases / "failure-classification.html",
    )
    fonts = output / "fonts"
    fonts.mkdir()
    for name in ("Geist-Variable.woff2", "GeistMono-Variable.woff2"):
        shutil.copyfile(ROOT / "web" / "src" / "fonts" / name, fonts / name)
    shutil.copyfile(ROOT / "web" / "public" / "geist-OFL.txt", fonts / "OFL.txt")
    media = ROOT / "docs" / "media"
    for name in (
        "demo-preview.png",
        "social-preview.png",
        "demo-walkthrough.gif",
        "demo-walkthrough.mp4",
    ):
        if (media / name).is_file():
            (output / "media").mkdir(exist_ok=True)
            shutil.copyfile(media / name, output / "media" / name)
    public: dict[str, Any] = {
        "schema_version": 1,
        "project_version": __version__,
        "source": "scripted",
        "demo": True,
        "model_requests": 0,
        "description": manifest["description"],
        "reproduce": "dm-agent-demo --output demo-run",
        "cases": [],
    }
    fixture = output / "fixture"
    fixture.mkdir()
    for name, source in (
        ("retry-before.py", demo_output / "before" / "retry.py"),
        ("retry-after.py", demo_output / "verified" / "retry.py"),
        ("test_retry.py", demo_output / "verified" / "test_retry.py"),
        ("repair.patch", demo_output / "verified.patch"),
    ):
        shutil.copyfile(source, fixture / name)
    public["fixture_sha256"] = {
        f"fixture/{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(fixture.iterdir())
    }
    for case in manifest["cases"]:
        name = case["id"]
        report = export_session_report(
            load_session_entries(demo_output / case["trace"]),
            source_name=f"{name}.jsonl",
            include_content=True,
            demo=True,
        )
        (output / f"{name}.html").write_text(report, encoding="utf-8")
        public["cases"].append(
            {
                "id": name,
                "report": f"{name}.html",
                "reported_status": case["status"],
                "step_count": case["step_count"],
                "test_returncodes": case["test_returncodes"],
                "verification_gap": case["verification_gap"],
            }
        )
    (output / "demo-manifest.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / ".nojekyll").touch()
    return public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/site"))
    args = parser.parse_args()
    raw = args.output.with_name(args.output.name + "-source")
    build_site(args.output, raw)
    print(f"Exhibit: {args.output.resolve()}")
    print(f"Original demo traces (not published): {raw.resolve()}")


if __name__ == "__main__":
    main()
