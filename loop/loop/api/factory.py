# loop/loop/api/factory.py
from __future__ import annotations
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from librarian.store import load_index
from librarian.embedding import Embedder
from librarian.query import Reranker

from ..runner import WarrantRunner
from ..worktree import WorktreeManager
from .invokers import AnthropicLLM, AnthropicInvoker, AnthropicVerifierInvoker


@dataclass
class ApiConfig:
    index_path: str
    out_dir: str
    base_repo: str
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    claude_model: str = "claude-sonnet-4-6"
    claude_model_verifier: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    max_tool_rounds: int = 50
    global_iteration_cap: int = 10
    per_node_attempt_cap: int = 3
    watchdog_timeout: float = 300.0
    max_parallel: int = 3
    max_principles: int = 15
    verify_iteration_cap: int = 3


def load_config(config_path: str | Path) -> ApiConfig:
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    known = {f.name for f in dataclasses.fields(ApiConfig)}
    filtered = {k: v for k, v in data.items() if k in known}
    return ApiConfig(**filtered)


def build_runner(config: ApiConfig) -> WarrantRunner:
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package required for the standalone CLI: "
            "pip install 'warrant[api]'"
        )
    index = load_index(config.index_path)
    embedder = Embedder(config.model_name)
    reranker = Reranker(config.reranker_name)
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    llm = AnthropicLLM(client, config.claude_model)
    invoker = AnthropicInvoker(client, config.claude_model, config.max_tool_rounds)
    verifier_invoker = AnthropicVerifierInvoker(
        client, config.claude_model_verifier, config.max_tool_rounds
    )
    worktree_mgr = WorktreeManager()
    return WarrantRunner(
        index=index,
        embedder=embedder,
        reranker=reranker,
        llm=llm,
        invoker=invoker,
        verifier_invoker=verifier_invoker,
        worktree_mgr=worktree_mgr,
        base_repo=Path(config.base_repo),
        out_dir=Path(config.out_dir),
        global_iteration_cap=config.global_iteration_cap,
        per_node_attempt_cap=config.per_node_attempt_cap,
        watchdog_timeout=config.watchdog_timeout,
        max_parallel=config.max_parallel,
        max_principles=config.max_principles,
        verify_iteration_cap=config.verify_iteration_cap,
    )
