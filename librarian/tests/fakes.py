import json


class FakeLLM:
    """Returns a queued response per complete() call. Records prompts."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def principles_json(items: list[dict]) -> str:
    return json.dumps(items)
