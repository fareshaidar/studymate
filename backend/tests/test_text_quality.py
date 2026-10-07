from app.config import settings
from app.rag.text_quality import alnum_ratio, strip_diagram_chars

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
