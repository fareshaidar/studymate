from app.llm.base import LLMClient


class FakeLLMClient(LLMClient):
    """Stand-in for a real LLM: returns canned text and records what it was asked.

    `replies`, if given, is used up one item per `generate` call, in order; an item
    that is an exception is raised instead of returned. This lets one test make the
    first call (e.g. a rewrite) fail and the next one (the answer) succeed.
    """

    def __init__(self, reply="Fake answer.", chunks=None, error=None, replies=None):
        self.reply = reply
        self.chunks = chunks if chunks is not None else [reply]
        self.error = error
        self.replies = list(replies) if replies is not None else None
        self.calls = []  # (prompt, system) pairs

    def generate(self, prompt, system=None):
        self.calls.append((prompt, system))
        if self.error:
            raise self.error
        if self.replies is not None:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return self.reply

    def stream(self, prompt, system=None):
        # A generator: the call is recorded when iteration starts, like a real stream.
        self.calls.append((prompt, system))
        if self.error:
            raise self.error
        yield from self.chunks
