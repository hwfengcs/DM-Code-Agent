"""Save one read-only GitHub growth snapshot; requires gh login and repository traffic access."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY = "hwfengcs/DM-Code-Agent"


def read_api(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{path}".rstrip("/")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="A new JSON file, preferably in build/"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new file to preserve the previous snapshot.")
    repo = read_api("")
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "stars": repo["stargazers_count"],
        "forks": repo["forks_count"],
        "views": read_api("traffic/views"),
        "clones": read_api("traffic/clones"),
        "referrers": read_api("traffic/popular/referrers"),
        "paths": read_api("traffic/popular/paths"),
        "interpretation": (
            "Traffic covers GitHub's rolling window, not lifetime traffic. "
            "Stars are cumulative snapshots. Star deltas divided by visitors are not "
            "a cohort conversion rate or proof that a particular post caused growth."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Saved {args.output}. Keep repository traffic data local unless you choose to share it.")


if __name__ == "__main__":
    main()
