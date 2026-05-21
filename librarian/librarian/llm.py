import os


class AnthropicLLM:
    """LLM implementation backed by the Anthropic API. `client` is injectable
    for tests; in production it defaults to a real anthropic.Anthropic()."""

    def __init__(self, model: str = "claude-sonnet-4-6", client=None,
                 max_tokens: int = 8000):
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def complete(self, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
