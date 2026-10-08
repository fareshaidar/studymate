"""A scripted stand-in for Gemini, for --fake-llm runs and the runner tests.

It picks a plausible reply from the system prompt, so the whole pipeline runs end
to end without an API key: answers cite passage [1], rewrites return one line,
and the judge always says "supported" / "same meaning".
The numbers it produces mean nothing; they only show the plumbing works.
"""

import re
from collections.abc import Iterator

from app.llm.base import LLMClient
from app.rag.prompts import REWRITE_SYSTEM_PROMPT, SYSTEM_PROMPT
from evaluation.judge_prompts import FAITHFULNESS_SYSTEM_PROMPT, REWRITE_JUDGE_SYSTEM_PROMPT

FAKE_ANSWER = "Fake answer based on the first passage [1]."


class ScriptedEvalLLM(LLMClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        if system == REWRITE_SYSTEM_PROMPT:
            # Echo the follow-up as the "standalone" question: one line, always usable.
            match = re.search(r"Follow-up question: (.+)", prompt)
            return match.group(1).strip() if match else "Fake standalone question?"
        if system == SYSTEM_PROMPT:
            return FAKE_ANSWER
        if system == FAITHFULNESS_SYSTEM_PROMPT:
            return '{"claims": [{"claim": "The fake answer\'s only claim.", "supported": true}]}'
        if system == REWRITE_JUDGE_SYSTEM_PROMPT:
            return '{"same_meaning": true}'
        raise ValueError("ScriptedEvalLLM got a system prompt it has no script for")

    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        yield self.generate(prompt, system=system)
