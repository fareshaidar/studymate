"""Small helpers for writing markdown reports: percentages with their n, tables, run info."""

import subprocess
from collections.abc import Sequence
from datetime import datetime

from app.config import settings
from evaluation.dataset import EVAL_DIR
from evaluation.metrics import Rate


def pct(r: Rate) -> str:
    """'60% (12/20)': always show the counts, since n is small."""
    if r.total == 0:
        return "– (0/0)"
    return f"{100 * r.count / r.total:.0f}% ({r.count}/{r.total})"


def num(value: float | None, digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines + [""]


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=EVAL_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def settings_snapshot() -> dict[str, object]:
    """The settings that affect retrieval and answers.

    The Gemini model name is left out on purpose: it may come from the owner's local
    configuration, which reports don't print.
    """
    return {
        "embedding_model": settings.embedding_model,
        "min_similarity": settings.min_similarity,
        "retrieval_top_k": settings.retrieval_top_k,
        "min_alnum_ratio": settings.min_alnum_ratio,
        "history_window": settings.history_window,
    }


def run_header(title: str) -> list[str]:
    lines = [f"# {title}", "", f"Run {datetime.now():%Y-%m-%d %H:%M}, commit `{git_commit()}`.", ""]
    lines += table(["Setting", "Value"], list(settings_snapshot().items()))
    return lines
