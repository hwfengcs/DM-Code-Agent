"""Check the published case's evidence integrity without replaying tools or calling a model."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.reproduce_maintenance_case import reproduce

ARTIFACTS = Path(__file__).resolve().parents[1] / "docs/case-studies/failure-classification"


def test_archived_artifacts_match_the_published_hashes_and_usage():
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text(encoding="utf-8"))
    for name, expected in evidence["artifact_sha256"].items():
        assert hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest() == expected, name
    requests = json.loads((ARTIFACTS / "requests.json").read_text(encoding="utf-8"))
    assert len(requests) == evidence["model_requests"]
    for name, total in evidence["usage"].items():
        assert sum(request["usage"].get(name, 0) for request in requests) == total
    report = (ARTIFACTS / "report.html").read_text(encoding="utf-8")
    assert "step limit without completion" in report
    assert "2 failed, 464 passed" in report
    assert "Scripted demonstration" not in report
    assert "C:\\Users\\" not in report
    assert "C:/Users/" not in report


def test_reproduction_refuses_to_replace_existing_evidence(tmp_path, monkeypatch):
    sentinel = tmp_path / "original.txt"
    sentinel.write_text("original evidence", encoding="utf-8")

    def forbidden(*args):
        raise AssertionError("An existing output must be rejected before Git runs")

    monkeypatch.setattr("scripts.reproduce_maintenance_case.git", forbidden)
    with pytest.raises(ValueError, match="preserved"):
        reproduce(tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "original evidence"
