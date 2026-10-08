"""Safety and fault-injection contracts for the opt-in ASMR scratch reaper."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest

from server.asmr_recovery import (
    MARKER, mark_asmr_job, sweep_abandoned_asmr_drafts,
)


def old_job(root: Path, name: str) -> Path:
    child = root / name
    child.mkdir()
    mark_asmr_job(child, "ana-paula-asmr-001")
    info = json.loads((child / MARKER).read_text(encoding="utf-8"))
    info["startedAtSeconds"] = time.time() - 90000
    (child / MARKER).write_text(json.dumps(info), encoding="utf-8")
    (child / "segment_00.mp4").write_bytes(b"partial-encoded-output")
    stale = time.time() - 90000
    os.utime(child / MARKER, (stale, stale))
    os.utime(child / "segment_00.mp4", (stale, stale))
    return child


def test_dry_run_is_default_and_cleanup_removes_only_marker_owned_abandoned_job(tmp_path):
    old = old_job(tmp_path, "abandoned")
    assert sweep_abandoned_asmr_drafts(tmp_path) == [old]
    assert old.exists(), "dry-run must never mutate files"
    removed = sweep_abandoned_asmr_drafts(tmp_path, dry_run=False)
    assert removed == [old]
    assert not old.exists()


def test_preserves_completed_recent_and_unrelated_directories(tmp_path):
    complete = old_job(tmp_path, "complete")
    (complete / "manifest.json").write_text("{}", encoding="utf-8")
    recent = tmp_path / "recent"
    recent.mkdir()
    mark_asmr_job(recent, "ana-paula-asmr-001")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "private.txt").write_text("keep", encoding="utf-8")
    assert sweep_abandoned_asmr_drafts(tmp_path, dry_run=False) == []
    assert complete.exists() and recent.exists() and unrelated.exists()


def test_unexpected_files_and_symlinks_are_never_deleted(tmp_path):
    unexpected = old_job(tmp_path, "foreign-file")
    (unexpected / "notes.txt").write_text("do not touch", encoding="utf-8")
    linked = old_job(tmp_path, "symlinked")
    (linked / "external").symlink_to(unexpected)
    outside = old_job(tmp_path, "file-symlink")
    (outside / "segment_00.mp4").unlink()
    (outside / "segment_00.mp4").symlink_to(unexpected / "notes.txt")
    assert sweep_abandoned_asmr_drafts(tmp_path, dry_run=False) == []
    assert all(x.exists() for x in (unexpected, linked, outside))


def test_rejects_unsafe_age_and_root(tmp_path):
    with pytest.raises(ValueError, match="3600"):
        sweep_abandoned_asmr_drafts(tmp_path, min_age_seconds=5)
    with pytest.raises(ValueError, match="trusted"):
        sweep_abandoned_asmr_drafts(tmp_path / "absent")
    symlink = tmp_path / "alias"
    symlink.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        sweep_abandoned_asmr_drafts(symlink)


def test_freshly_touched_old_job_is_not_swept(tmp_path):
    old = old_job(tmp_path, "active")
    os.utime(old / "segment_00.mp4", None)
    assert sweep_abandoned_asmr_drafts(tmp_path, dry_run=False) == []
    assert old.exists()
