import pytest
from pathlib import Path
from loop import runstore


def test_load_latest_run_raises_when_no_runs(tmp_path):
    """resume path: out_dir exists but has no run files — expect FileNotFoundError."""
    out_dir = tmp_path / "runs"
    out_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        runstore.load_latest_run(out_dir)
