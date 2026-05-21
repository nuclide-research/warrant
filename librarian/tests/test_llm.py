from librarian.llm import AnthropicLLM


class _StubMessages:
    def __init__(self, recorder):
        self._rec = recorder

    def create(self, **kwargs):
        self._rec.update(kwargs)

        class _Block:
            text = "STUB RESPONSE"

        class _Msg:
            content = [_Block()]

        return _Msg()


class _StubClient:
    def __init__(self, recorder):
        self.messages = _StubMessages(recorder)


def test_anthropic_llm_sends_prompt_and_returns_text():
    rec: dict = {}
    llm = AnthropicLLM(model="claude-sonnet-4-6", client=_StubClient(rec))
    out = llm.complete("hello")
    assert out == "STUB RESPONSE"
    assert rec["model"] == "claude-sonnet-4-6"
    assert rec["messages"][0]["content"] == "hello"
    assert rec["max_tokens"] == llm.max_tokens
