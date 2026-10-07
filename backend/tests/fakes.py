from app.llm.base import LLMClient


class FakeLLMClient(LLMClient):
    """Stand-in for a real LLM: returns canned text and records what it was asked."""

    def __init__(self, reply="Fake answer.", chunks=None, error=None):
        self.reply = reply
        self.chunks = chunks if chunks is not None else [reply]
        self.error = error
        self.calls = []  # (prompt, system) pairs

    def generate(self, prompt, system=None):
        self.calls.append((prompt, system))
        if self.error:
            raise self.error
        return self.reply

    def stream(self, prompt, system=None):
        # A generator: the call is recorded when iteration starts, like a real stream.
        self.calls.append((prompt, system))
        if self.error:
            raise self.error
        yield from self.chunks
