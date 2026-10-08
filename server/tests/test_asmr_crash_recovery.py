"""Fail-closed SIGKILL contract for ASMR scratch material; no Railway side effects."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from server.asmr_reels import AsmrDraftIntegrityError, verify_asmr_draft


@pytest.mark.skipif(os.name != "posix", reason="SIGKILL requires POSIX")
def test_sigkill_interrupted_writer_can_never_claim_completed_video(tmp_path: Path) -> None:
    """Kill a writer after it creates a real on-disk, unfinished job.

    This is a process-crash contract, not a Railway restart or FFmpeg-load test.
    """
    root = tmp_path / "scratch"
    signal_file = tmp_path / "written"
    code = (
        "from pathlib import Path\n"
        "import sys,time\n"
        "root=Path(sys.argv[1]); ready=Path(sys.argv[2])\n"
        "root.mkdir(); (root/'segment_00.mp4').write_bytes(b'partial')\n"
        "ready.write_text('ok',encoding='utf-8')\n"
        "time.sleep(30)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(root), str(signal_file)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 8.0
        while not signal_file.exists() and time.monotonic() < deadline:
            if child.poll() is not None:
                raise AssertionError("writer exited before checkpoint")
            time.sleep(0.05)
        assert signal_file.exists(), "writer checkpoint not reached"
        child.kill()
        assert child.wait(timeout=5) != 0
        assert (root / "segment_00.mp4").is_file()
        with pytest.raises(AsmrDraftIntegrityError, match="missing|incomplete"):
            verify_asmr_draft(root)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
