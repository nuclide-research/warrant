"""Import-level and construction smoke test — fails fast on any wiring error."""
import json
import subprocess
from pathlib import Path


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_all_imports():
    import loop.models
    import loop.runstore
    import loop.worktree
    import loop.materializer
    import loop.phases.orient
    import loop.phases.retrieve
    import loop.phases.plan
    import loop.phases.execute
    import loop.runner


def test_runner_construction_and_run(tmp_path):
    from loop.runner import WarrantRunner
    from loop.worktree import WorktreeManager
    from loop.models import ExecutorResult
    from tests.fakes import FakeLLM, FakeInvoker, FakeReranker, FakeEmbedder, make_fixture_index

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    llm = FakeLLM()
    llm.queue("I am a specialist.")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "X", "approach": "Y", "grounds": []}]))

    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))

    runner = WarrantRunner(
        index=make_fixture_index(2),
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        llm=llm,
        invoker=invoker,
        worktree_mgr=WorktreeManager(),
        base_repo=repo,
        out_dir=tmp_path / "out",
        global_iteration_cap=3,
    )
    final_rs = runner.run("build a thing")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert final_rs.phase == "done"
