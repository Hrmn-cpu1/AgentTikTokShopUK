"""Explicit, conservative cleanup of abandoned ASMR scratch renders.

Never scans persistent promoted media and never deletes a completed manifest.
Dry-run by default. The caller must choose a dedicated trusted scratch root.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
import uuid

MARKER = ".asmr-job-owner.json"
SCHEMA = "agencyos-asmr-scratch-v1"
MIN_SWEEP_AGE_SECONDS = 3600
ALLOWED_NAMES = {
    MARKER, ".reel-incomplete.mp4", ".manifest-incomplete.json",
    "reel.mp4", "thumbnail.jpg", "segments.ffconcat", "combined_video.mp4",
}
SEGMENT_PATTERN = re.compile(r"segment_[0-9]{2}\.mp4\Z")


def mark_asmr_job(directory: Path, creative_id: str) -> None:
    """Create an exclusive ownership marker inside an already claimed empty job dir."""
    marker = directory / MARKER
    payload = {
        "schema": SCHEMA, "creativeId": creative_id,
        "startedAtSeconds": time.time(), "pid": os.getpid(),
    }
    with marker.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def _eligible(candidate: Path, now_seconds: float, min_age_seconds: float) -> bool:
    """Only trust marker + known scratch file names; never follow child symlinks."""
    if candidate.is_symlink() or not candidate.is_dir():
        return False
    marker = candidate / MARKER
    manifest = candidate / "manifest.json"
    if manifest.exists() or manifest.is_symlink():
        return False
    if marker.is_symlink() or not marker.is_file():
        return False
    try:
        if not 0 < marker.stat().st_size <= 2048:
            return False
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            return False
        started = data.get("startedAtSeconds")
        if (type(started) not in (float, int)
                or not math.isfinite(started)
                or started > now_seconds - min_age_seconds):
            return False
        creative_id = data.get("creativeId")
        if not isinstance(creative_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{5,80}", creative_id):
            return False
        for item in candidate.iterdir():
            if item.is_symlink() or not item.is_file():
                return False
            if item.name not in ALLOWED_NAMES and SEGMENT_PATTERN.fullmatch(item.name) is None:
                return False
            if item.stat().st_mtime > now_seconds - min_age_seconds:
                return False
        return True
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError):
        return False


def sweep_abandoned_asmr_drafts(
    scratch_root: str | Path, *, min_age_seconds: int = 86400,
    dry_run: bool = True,
) -> list[Path]:
    """Identify, optionally remove abandoned jobs older than an explicit threshold.

    A fresh or completed render is never intentionally removed. Not guaranteed
    safe against an adversary able to modify the scratch root concurrently.
    Never point this at /data/media or a shared/untrusted filesystem.
    """
    if type(min_age_seconds) is not int or min_age_seconds < MIN_SWEEP_AGE_SECONDS:
        raise ValueError("minimum sweep age is 3600 seconds")
    if type(dry_run) is not bool:
        raise TypeError("dry_run must be boolean")
    root = Path(scratch_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("trusted scratch root must exist and not be a symlink")
    now = time.time()
    eligible: list[Path] = []
    for candidate in sorted(root.iterdir()):
        if not _eligible(candidate, now, min_age_seconds):
            continue
        eligible.append(candidate)
        if dry_run:
            continue
        tombstone = root / f".asmr-reaping-{uuid.uuid4().hex}"
        candidate.rename(tombstone)
        # Re-evaluate after exclusive same-filesystem move. No manifest => unclaimed.
        if not _eligible(tombstone, now, min_age_seconds):
            if not candidate.exists():
                tombstone.rename(candidate)
            raise RuntimeError("job changed during cleanup; scratch preserved")
        shutil.rmtree(tombstone)
    return eligible


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative ASMR abandoned-scratch reaper")
    parser.add_argument("--root", required=True, help="private dedicated scratch jobs root")
    parser.add_argument("--age-hours", type=int, default=24)
    parser.add_argument("--delete", action="store_true", help="remove only eligible abandoned jobs")
    args = parser.parse_args()
    found = sweep_abandoned_asmr_drafts(
        args.root, min_age_seconds=args.age_hours * 3600,
        dry_run=not args.delete,
    )
    print(json.dumps({"mode": "DELETE" if args.delete else "DRY_RUN",
                      "eligible": [str(x) for x in found]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
