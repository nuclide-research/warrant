from __future__ import annotations
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import loop.api.__main__ as m


def test_init_writes_correct_json(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=[".", "sample-library/index", ".warrant/runs"]):
        m.cmd_init(argparse.Namespace())
    data = json.loads(out_path.read_text())
    assert data == {
        "index_path": "sample-library/index",
        "base_repo": ".",
        "out_dir": ".warrant/runs",
    }


def test_init_uses_defaults_on_blank_input(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=["", "", ""]):
        m.cmd_init(argparse.Namespace())
    data = json.loads(out_path.read_text())
    assert data["base_repo"] == "."
    assert data["index_path"] == "sample-library/index"
    assert data["out_dir"] == ".warrant/runs"


def test_init_uses_custom_values(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=["/my/repo", "/my/index", "/my/runs"]):
        m.cmd_init(argparse.Namespace())
    data = json.loads(out_path.read_text())
    assert data["base_repo"] == "/my/repo"
    assert data["index_path"] == "/my/index"
    assert data["out_dir"] == "/my/runs"


def test_init_declines_overwrite(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    out_path.parent.mkdir(parents=True)
    out_path.write_text('{"base_repo": "original"}')
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=["n"]):
        m.cmd_init(argparse.Namespace())
    assert json.loads(out_path.read_text())["base_repo"] == "original"


def test_init_overwrites_on_y(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    out_path.parent.mkdir(parents=True)
    out_path.write_text('{"base_repo": "original"}')
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=["y", "/new/repo", "/new/index", "/new/runs"]):
        m.cmd_init(argparse.Namespace())
    assert json.loads(out_path.read_text())["base_repo"] == "/new/repo"


def test_init_creates_warrant_dir(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    assert not out_path.parent.exists()
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=[".", "sample-library/index", ".warrant/runs"]):
        m.cmd_init(argparse.Namespace())
    assert out_path.parent.is_dir()


def test_main_init_subcommand_routes_to_cmd_init(tmp_path):
    out_path = tmp_path / ".warrant" / "api-config.json"
    with patch.object(m, "_INIT_OUTPUT", out_path), \
         patch("builtins.input", side_effect=[".", "sample-library/index", ".warrant/runs"]), \
         patch("sys.argv", ["warrant", "init"]):
        m.main()
    assert out_path.exists()


def test_default_config_path_is_api_config():
    assert str(m._DEFAULT_CONFIG) == ".warrant/api-config.json"
