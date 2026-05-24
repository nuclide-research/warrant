import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from loop.skill.factory import Config, load_config, build_runner
from loop.runner import WarrantRunner


def test_load_config_reads_json(tmp_path):
    cfg_data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/myproject",
        "global_iteration_cap": 5,
        "per_node_attempt_cap": 2,
        "watchdog_timeout": 120.0,
        "max_parallel": 2,
        "max_principles": 10,
        "verify_iteration_cap": 2,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg_data))

    result = load_config(config_file)

    assert result.index_path == "/data/index"
    assert result.out_dir == ".warrant/runs"
    assert result.base_repo == "/code/myproject"
    assert result.global_iteration_cap == 5
    assert result.per_node_attempt_cap == 2
    assert result.watchdog_timeout == 120.0
    assert result.max_parallel == 2
    assert result.max_principles == 10
    assert result.verify_iteration_cap == 2


def test_load_config_defaults(tmp_path):
    cfg_data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/myproject",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg_data))

    result = load_config(config_file)

    assert result.global_iteration_cap == 10
    assert result.per_node_attempt_cap == 3
    assert result.watchdog_timeout == 300.0
    assert result.max_parallel == 3
    assert result.max_principles == 15
    assert result.verify_iteration_cap == 3
    assert result.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert result.reranker_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_build_runner_wires_components(tmp_path):
    cfg = Config(
        index_path=str(tmp_path / "index"),
        out_dir=str(tmp_path / "runs"),
        base_repo=str(tmp_path / "repo"),
    )
    fake_index = MagicMock()
    with patch("loop.skill.factory.load_index", return_value=fake_index) as mock_idx, \
         patch("loop.skill.factory.Embedder") as mock_emb, \
         patch("loop.skill.factory.Reranker") as mock_rnk:
        runner = build_runner(cfg)

    mock_idx.assert_called_once_with(cfg.index_path)
    mock_emb.assert_called_once_with(cfg.model_name)
    mock_rnk.assert_called_once_with(cfg.reranker_name)
    assert isinstance(runner, WarrantRunner)
