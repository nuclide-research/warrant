from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loop.api.factory import ApiConfig, load_config, build_runner
from loop.runner import WarrantRunner


def test_load_config_reads_all_fields(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
        "claude_model": "claude-opus-4-7",
        "claude_model_verifier": "claude-haiku-4-5-20251001",
        "anthropic_api_key": "sk-test-123",
        "max_tool_rounds": 20,
        "global_iteration_cap": 5,
        "per_node_attempt_cap": 2,
        "watchdog_timeout": 60.0,
        "max_parallel": 2,
        "max_principles": 8,
        "verify_iteration_cap": 2,
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))

    cfg = load_config(cfg_file)

    assert cfg.index_path == "/data/index"
    assert cfg.claude_model == "claude-opus-4-7"
    assert cfg.claude_model_verifier == "claude-haiku-4-5-20251001"
    assert cfg.anthropic_api_key == "sk-test-123"
    assert cfg.max_tool_rounds == 20
    assert cfg.global_iteration_cap == 5


def test_load_config_applies_defaults(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))

    cfg = load_config(cfg_file)

    assert cfg.claude_model == "claude-sonnet-4-6"
    assert cfg.claude_model_verifier == "claude-sonnet-4-6"
    assert cfg.anthropic_api_key is None
    assert cfg.max_tool_rounds == 50
    assert cfg.global_iteration_cap == 10
    assert cfg.per_node_attempt_cap == 3
    assert cfg.watchdog_timeout == 300.0
    assert cfg.max_parallel == 3
    assert cfg.max_principles == 15
    assert cfg.verify_iteration_cap == 3
    assert cfg.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.reranker_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_load_config_ignores_unknown_fields(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
        "unknown_field_xyz": "ignored",
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))
    cfg = load_config(cfg_file)  # must not raise
    assert cfg.index_path == "/data/index"


def test_build_runner_wires_components(tmp_path):
    cfg = ApiConfig(
        index_path=str(tmp_path / "index"),
        out_dir=str(tmp_path / "runs"),
        base_repo=str(tmp_path / "repo"),
        claude_model="claude-sonnet-4-6",
        global_iteration_cap=7,
        per_node_attempt_cap=2,
        watchdog_timeout=60.0,
        max_parallel=2,
        max_principles=8,
        verify_iteration_cap=2,
        max_tool_rounds=10,
    )
    fake_index = MagicMock()
    # anthropic is lazily imported inside build_runner; patch it on the real module
    with patch("loop.api.factory.load_index", return_value=fake_index), \
         patch("loop.api.factory.Embedder") as mock_emb, \
         patch("loop.api.factory.Reranker") as mock_rnk, \
         patch("anthropic.Anthropic", return_value=MagicMock()):
        runner = build_runner(cfg)

    assert isinstance(runner, WarrantRunner)
    assert runner._cfg["global_iteration_cap"] == 7
    assert runner._cfg["per_node_attempt_cap"] == 2
    assert runner._cfg["watchdog_timeout"] == 60.0
    assert runner._cfg["max_parallel"] == 2
    assert runner._max_principles == 8
    assert runner._verify_iteration_cap == 2
    mock_emb.assert_called_once_with(cfg.model_name)
    mock_rnk.assert_called_once_with(cfg.reranker_name)


import sys
from loop.api import __main__ as api_main


def test_main_run_calls_runner(tmp_path):
    cfg_data = {
        "index_path": str(tmp_path / "index"),
        "out_dir": str(tmp_path / "runs"),
        "base_repo": str(tmp_path / "repo"),
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg_data))

    fake_runner = MagicMock()
    fake_run_state = MagicMock()
    fake_run_state.worktree_path = "/tmp/wt"
    fake_report = MagicMock()
    fake_runner.run.return_value = (fake_run_state, fake_report)

    with patch("loop.api.__main__.load_config") as mock_cfg, \
         patch("loop.api.__main__.build_runner", return_value=fake_runner), \
         patch("loop.api.__main__.render_citation_report", return_value="report text"), \
         patch("sys.argv", ["warrant", "run", "--direction", "build a cache layer",
                            "--config", str(cfg_file)]):
        mock_cfg.return_value = MagicMock(out_dir=str(tmp_path / "runs"))
        api_main.main()

    fake_runner.run.assert_called_once_with("build a cache layer")
