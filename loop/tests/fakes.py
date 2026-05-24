from __future__ import annotations
import numpy as np
from loop.models import ExecutorResult, CheckResult, VerifierResult, VerifierCheckOutcome
from librarian.models import Principle, Citation, Edge
from librarian.store import Index


class FakeLLM:
    """Queue responses with .queue(text); falls back to default."""

    def __init__(self, default: str = "[]"):
        self._responses: list[str] = []
        self._default = default

    def queue(self, response: str) -> None:
        self._responses.append(response)

    def __call__(self, prompt: str) -> str:
        if self._responses:
            return self._responses.pop(0)
        return self._default


class FakeInvoker:
    """Queue results with .queue(result); falls back to a generic done result."""

    def __init__(self):
        self._results: list[ExecutorResult] = []

    def queue(self, result: ExecutorResult) -> None:
        self._results.append(result)

    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult:
        if self._results:
            return self._results.pop(0)
        return ExecutorResult(
            node_id="unknown",
            status="done",
            checks_run=[],
            principles_honored=[],
            principles_violated=[],
            amendments=[],
            summary="fake done",
        )


class FakeReranker:
    def rerank(self, query: str, candidates):
        return [(c, float(i)) for i, c in enumerate(reversed(candidates))]


class FakeEmbedder:
    def encode(self, texts):
        return np.zeros((len(texts), 4))


def make_fixture_principle(pid: str = "test-book:ch1:s1", statement: str = "Prefer composition over inheritance.") -> Principle:
    return Principle(
        id=pid,
        statement=statement,
        citation=Citation(
            book="Test Book",
            isbn="9999999999999",
            chapter="Chapter 1",
            section="Section 1",
        ),
        checkability_tier=2,
        evidence_chunk="Composition leads to more flexible designs.",
    )


def make_fixture_index(n: int = 2) -> Index:
    principles = [
        make_fixture_principle(
            pid=f"test-book:ch1:s{i}",
            statement=f"Principle {i}.",
        )
        for i in range(1, n + 1)
    ]
    embeddings = np.zeros((n, 4))
    return Index(principles=principles, embeddings=embeddings, edges=[])


class FakeVerifierInvoker:
    """Queue VerifierResults with .queue(result); falls back to a generic pass result."""

    def __init__(self):
        self._results: list[VerifierResult] = []

    def queue(self, result: VerifierResult) -> None:
        self._results.append(result)

    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult:
        if self._results:
            return self._results.pop(0)
        return VerifierResult(
            node_id="unknown",
            verdict="pass",
            confidence=1.0,
            check_outcomes=[],
            integrity_verdict="clean",
            summary="fake pass",
        )


def make_pass_verifier_result(node_id: str) -> VerifierResult:
    return VerifierResult(
        node_id=node_id,
        verdict="pass",
        confidence=1.0,
        check_outcomes=[],
        integrity_verdict="clean",
        summary="all checks passed",
    )
