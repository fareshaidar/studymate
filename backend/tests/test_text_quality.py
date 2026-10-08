import pytest

from app.config import settings
from app.rag.text_quality import (
    MAX_WORDS_PER_DOT_LEADER,
    MIN_DOT_LEADERS,
    alnum_ratio,
    count_dot_leaders,
    count_words,
    is_front_matter,
    strip_diagram_chars,
)

FLOWCHART = (
    "└────────┬────────┘ ↓ ┌─────────────────┐ │ Crossover │ └────────┬────────┘ "
    "↓ ┌─────────────────┐ │ Mutation │ └────────┬────────┘ ↓ ┌──────┐ │ Stop │ └──────┘"
)
RESULTS_TABLE = (
    "Configuration Best cost Time (s) Std dev\n"
    "Baseline 1201.8 29.8 1.498591\n"
    "Population 1000 1188.2 58.1 1.201377\n"
    "Mutation 0.05 1215.4 30.2 2.004410"
)
PROSE = "The algorithm terminates after a fixed number of non-improving generations."


def test_prose_scores_high():
    assert alnum_ratio(PROSE) > 0.95


def test_flowchart_scores_low():
    assert alnum_ratio(FLOWCHART) < settings.min_alnum_ratio


def test_numeric_table_survives_but_flowchart_does_not():
    assert alnum_ratio("Baseline 1201.8 29.8 1.498591") >= settings.min_alnum_ratio
    assert alnum_ratio(RESULTS_TABLE) >= settings.min_alnum_ratio
    assert alnum_ratio(FLOWCHART) < settings.min_alnum_ratio


def test_code_and_formulas_survive():
    code = "for i in range(n_gen):\n    pop = mutate(select(pop, k=50), rate=0.02)"
    formula = "fitness = 1 / (cost + 1e-9)"
    assert alnum_ratio(code) >= settings.min_alnum_ratio
    assert alnum_ratio(formula) >= settings.min_alnum_ratio


def test_text_with_a_small_diagram_survives():
    mixed = "│ Counter < n_gen ? │ └───┬───┘ " + PROSE + " " + PROSE
    assert alnum_ratio(mixed) >= settings.min_alnum_ratio


def test_empty_text_scores_zero():
    assert alnum_ratio("") == 0.0
    assert alnum_ratio("   \n ") == 0.0


def test_strip_diagram_chars_keeps_words_and_numbers():
    text = "│ Counter < n_gen ? │ └───┬───┘ ↓ ┌──┐ │ Return Best │ Baseline 1201.8 → done"
    assert strip_diagram_chars(text) == "Counter < n_gen ? Return Best Baseline 1201.8 done"


def test_strip_diagram_chars_leaves_plain_text_alone():
    assert strip_diagram_chars(PROSE) == PROSE
    assert strip_diagram_chars("Line one\nLine two") == "Line one\nLine two"


# --- Front matter (tables of contents, lists of figures) ---

TABLE_OF_CONTENTS = (
    "TABLE OF CONTENTS\n"
    "INTRODUCTION ................ 1\n"
    "Water System ................ 5\n"
    "Food System ................. 12\n"
    "Sleep Compartment ........... 20\n"
    "Personal Hygiene ............ 31\n"
    "Waste Management ............ 44"
)
# OCR often reads leaders as spaced dots.
LIST_OF_FIGURES = "\n".join(
    f"Figure {n}. Storage tank layout . . . . . . . {20 + n}" for n in range(1, 7)
)


def test_count_dot_leaders():
    assert count_dot_leaders("Water System ........ 5") == 1
    assert count_dot_leaders("Water . . . . 5") == 1  # OCR spacing
    assert count_dot_leaders("A ....... 1 B ....... 2") == 2
    assert count_dot_leaders("He waited... then left.") == 0  # an ellipsis is not a leader
    assert count_dot_leaders(PROSE) == 0


def test_count_words_ignores_runs_of_dots():
    assert count_words("Water . . . . . 12") == 2
    assert count_words("Water System ........ 5") == 3


def test_table_of_contents_and_list_of_figures_are_front_matter():
    assert is_front_matter(TABLE_OF_CONTENTS)
    assert is_front_matter(LIST_OF_FIGURES)


@pytest.mark.parametrize(
    "text",
    [
        PROSE,
        RESULTS_TABLE,
        "As shown in Figure 3 and Figure 4, the ten tanks held the water. See Table 2.",
        "The crew waited... and waited... then the water finally flowed...",
        "",
    ],
)
def test_body_text_is_not_front_matter(text):
    assert not is_front_matter(text)


def passage(leaders: int, words: int) -> str:
    """`words` words, the first `leaders` of them each followed by a dot leader.

    Real leaders always have words or page numbers between them; leaders joined only
    by spaces would read as one long spaced-out leader.
    """
    return " ".join(["word ...."] * leaders + ["word"] * (words - leaders))


def test_a_few_stray_leaders_in_a_long_passage_are_not_front_matter():
    # Like an OCR'd diagram page: 8 leaders in 170 words is below one per 18 words.
    diagram = passage(8, 170)
    assert (count_dot_leaders(diagram), count_words(diagram)) == (8, 170)
    assert not is_front_matter(diagram)


def test_boundaries_of_the_rule():

    # Dense enough but too few leaders: a short list with 4 entries isn't flagged.
    assert not is_front_matter(passage(MIN_DOT_LEADERS - 1, 10))
    # Exactly one leader per 18 words counts; one word more does not.
    words = MIN_DOT_LEADERS * MAX_WORDS_PER_DOT_LEADER
    assert is_front_matter(passage(MIN_DOT_LEADERS, words))
    assert not is_front_matter(passage(MIN_DOT_LEADERS, words + 1))
