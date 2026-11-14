"""The public exhibit publishes fixtures, never the private source trace container."""

import json
from pathlib import Path

import pytest

from scripts.build_demo_site import build_site


def test_public_exhibit_contains_evidence_without_local_paths(tmp_path: Path) -> None:
    output, raw = tmp_path / "public", tmp_path / "private-source"
    manifest = build_site(output, raw)
    assert manifest["cases"][0]["test_returncodes"] == [1, 0]
    assert manifest["cases"][1]["verification_gap"] is True
    assert (raw / "sessions" / "verified.jsonl").is_file()
    assert not list(output.rglob("*.jsonl"))
    case_report = (output / "cases" / "failure-classification.html").read_text(encoding="utf-8")
    assert "step limit without completion" in case_report
    assert "2 failed, 464 passed" in case_report
    assert json.loads((output / "demo-manifest.json").read_text()) == manifest
    for name in ("verified.html", "unverified.html", "demo-manifest.json"):
        content = (output / name).read_text(encoding="utf-8")
        for private in (str(tmp_path), str(Path.home())):
            assert private not in content
            assert private.replace("\\", "/") not in content
        assert "Scripted" in content or '"source": "scripted"' in content


@pytest.mark.parametrize("nested", ["same", "raw_inside_public", "public_inside_raw"])
def test_raw_logs_cannot_be_published_by_directory_overlap(tmp_path: Path, nested: str) -> None:
    output = tmp_path / "public"
    raw = output if nested == "same" else output / "raw"
    if nested == "public_inside_raw":
        output, raw = raw, output
    with pytest.raises(ValueError, match="separate"):
        build_site(output, raw)
    assert not output.exists()


def test_build_preserves_existing_files(tmp_path: Path) -> None:
    marker = tmp_path / "do-not-replace.txt"
    marker.write_text("keep me")
    with pytest.raises(ValueError, match="new or empty"):
        build_site(tmp_path, tmp_path / "source")
    assert marker.read_text() == "keep me"
