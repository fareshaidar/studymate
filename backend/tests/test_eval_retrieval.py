import json

import pytest

from app.config import settings
from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore
from app.services.chat import retrieve
from evaluation.harness import BACKEND_DATA_DIR, EvalIndex, UnsafePathError
from evaluation.metrics import RankingMetrics, Rate, kept_chunks
from evaluation.run_retrieval_eval import _hit_rate, evaluate, main, rank
from tests.test_eval_dataset import answerable, make_dataset

GA = "A genetic algorithm evolves a population of candidate solutions over many generations."
SELECTION = "Selection keeps the fittest individuals so that good solutions survive and reproduce."
MUTATION = "Mutation randomly changes genes, which adds variety and helps escape local optima."
CROSSOVER = "Crossover combines two parent solutions to create children in a genetic algorithm."
PIZZA = "Pepperoni pizza is baked with mozzarella cheese and tomato sauce in a hot oven."
DIAGRAM = "┌──────┐ │ Genetic │ └──┬───┘ ↓ ┌──────┐ │ algorithm │ └──┬───┘ ↓ ┌────┐ │ Stop │ └────┘"


def test_kept_chunks_and_retrieve_keep_the_same_chunks(tmp_path):
    """The sweeps re-implement retrieve()'s cutoff on recorded rankings; this keeps them in step."""
    store = VectorStore(path=tmp_path / "chroma")
    texts = [GA, DIAGRAM, SELECTION, MUTATION, CROSSOVER, PIZZA, DIAGRAM + " selection", GA + "!"]
    store.add_chunks("app1", [Chunk(text=t, page=i + 1, index=i) for i, t in enumerate(texts)])
    index = EvalIndex(session=None, store=store, app_ids={"ga": "app1"}, dataset_ids={"app1": "ga"})
    queries = ["How does a genetic algorithm work?", "What does selection do?", "pizza", "diagram"]

    compared = 0
    for query in queries:
        ranking = rank(query, index)
        for threshold in (0.0, 0.5, 0.6, 0.7, 0.9):
            for top_k in (1, 2, 3, 5):
                expected = retrieve(query, ["app1"], store, top_k=top_k, min_similarity=threshold)
                from_pipeline = [(r.page, r.chunk_index) for r in expected.kept]
                from_sweep = [
                    (c.page[1], c.chunk_index) for c in kept_chunks(ranking, threshold, top_k)
                ]
                assert from_sweep == from_pipeline, (query, threshold, top_k)
                compared += bool(from_pipeline)
    # The comparison isn't vacuous: plenty of settings keep something.
    assert compared > 20
    # And the diagram chunk really is in the rankings, so the usable filter is exercised.
    assert any(not c.usable for c in rank("genetic algorithm diagram", index)[:4])


# One entry per line, as on a real contents page (the test PDF helper doesn't wrap lines).
CONTENTS = "TABLE OF CONTENTS\n" + "\n".join(
    f"Section {n}. Genetic algorithm selection and mutation .... {n * 3}" for n in range(1, 8)
)


def test_kept_chunks_and_retrieve_agree_with_the_front_matter_filter_on(tmp_path, monkeypatch):
    """The same drift check with exclude_front_matter on: retrieve() drops front matter
    through is_usable(), the sweeps through the recorded front_matter flag."""
    monkeypatch.setattr(settings, "exclude_front_matter", True)
    store = VectorStore(path=tmp_path / "chroma")
    texts = [CONTENTS, GA, SELECTION, MUTATION, CROSSOVER, PIZZA]
    store.add_chunks("app1", [Chunk(text=t, page=i + 1, index=i) for i, t in enumerate(texts)])
    index = EvalIndex(session=None, store=store, app_ids={"ga": "app1"}, dataset_ids={"app1": "ga"})

    ranking = rank("genetic algorithm selection and mutation", index)
    # The contents chunk really ranks high, so the filter is exercised.
    assert any(c.front_matter for c in ranking[:3])
    for top_k in (1, 2, 3, 5):
        expected = retrieve("genetic algorithm selection and mutation", ["app1"], store,
                            top_k=top_k, min_similarity=0.0)
        from_pipeline = [(r.page, r.chunk_index) for r in expected.kept]
        from_sweep = [
            (c.page[1], c.chunk_index)
            for c in kept_chunks(ranking, 0.0, top_k, drop_front_matter=True)
        ]
        assert from_sweep == from_pipeline, top_k
        assert 1 not in [page for page, _ in from_pipeline]  # the contents page is gone


PAGES = [GA + " " + MUTATION, SELECTION, PIZZA]


def tiny_dataset(tmp_path):
    items = [
        answerable(
            id="a1", question="What does mutation add?", pages=[1], evidence=["adds variety"]
        ),
        answerable(
            id="a2",
            question="Why keep the fittest individuals?",
            pages=[2],
            evidence=["keeps the fittest"],
            author="user",
        ),
        answerable(
            id="f1",
            type="follow_up",
            question="And what does it keep?",
            history=[{"role": "user", "content": "What is selection?"}],
            expected_standalone="What does selection keep in a genetic algorithm?",
            pages=[2],
            evidence=["keeps the fittest"],
        ),
        unanswerable("off", "unanswerable_off_topic", "Who won the World Cup?"),
        unanswerable("on", "unanswerable_on_topic", "Who invented genetic algorithms?"),
    ]
    return make_dataset(tmp_path, items, pages=PAGES)


def unanswerable(item_id, question_type, question):
    return {"id": item_id, "type": question_type, "question": question, "reference_answer": "-"}


def args(tmp_path, out):
    dataset = str(tmp_path / "dataset.json")
    return ["--dataset", dataset, "--documents", str(tmp_path), "--out", str(out)]


def test_end_to_end_writes_json_and_report(tmp_path):
    dataset = tiny_dataset(tmp_path)
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    out = tmp_path / "results"

    code = main(args(tmp_path, out))

    assert code == 0
    report = (out / "retrieval-report.md").read_text(encoding="utf-8")
    for heading in (
        "## Ranking quality",
        "## Best score per question",
        "## min_similarity sweep",
        "## retrieval_top_k sweep",
        "## min_alnum_ratio",
        "never used to choose settings",
    ):
        assert heading in report
    assert "| held-out (owner-written) | 1 |" in report
    # a1 + the follow-up; a2 is held-out (author "user") and only in its own row.
    assert "| all (tuning set) | 2 |" in report
    (json_file,) = out.glob("retrieval-*.json")
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["counts"] == {  # tuning set only
        "answerable": 1,
        "follow_up": 1,
        "unanswerable_off_topic": 1,
        "unanswerable_on_topic": 1,
    }
    assert data["held_out_counts"] == {"answerable": 1}
    a1 = next(c for c in data["cases"] if c["item_id"] == "a1")
    assert a1["ranking"][0]["page"] == ["ga", 1]  # the mutation page ranks first
    # No document text in the results.
    assert all("text" not in r for case in data["cases"] for r in case["ranking"])
    assert "## Front-matter filter (Phase 9)" in report
    assert (out / "front-matter-audit.md").exists()


def test_output_inside_backend_data_is_refused(tmp_path):
    dataset = tiny_dataset(tmp_path)
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    target = BACKEND_DATA_DIR / "eval-results-test"

    with pytest.raises(UnsafePathError):
        main(args(tmp_path, target))
    assert not target.exists()


def test_hit_rate_turns_the_mean_back_into_counts():
    metrics = RankingMetrics(n=39, hit={1: 26 / 39, 5: 35 / 39}, recall={}, mrr=0.5)

    assert _hit_rate(metrics, 1) == Rate(26, 39)
    assert _hit_rate(metrics, 5) == Rate(35, 39)


def test_chunk_size_table_prints_counts(tmp_path):
    dataset = tiny_dataset(tmp_path)
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    out = tmp_path / "results"

    main(args(tmp_path, out) + ["--chunk-sweep"])

    report = (out / "retrieval-report.md").read_text(encoding="utf-8")
    section = report.split("## Chunk size")[1]
    rows = [line for line in section.splitlines() if line.startswith("| 1000 ")
            or line.startswith("| 1800 ") or line.startswith("| 2500 ")]
    assert len(rows) == 3
    for row in rows:
        hit_1, hit_5 = row.split(" | ")[3:5]
        # n = 2: the held-out item a2 never takes part in choosing a chunk size.
        assert hit_1.endswith("/2)") and hit_5.endswith("/2)")  # e.g. "50% (1/2)"


def test_held_out_items_never_change_tuning_results(tmp_path):
    """Removing the owner-written items must leave every sweep and tuning row identical,
    so they can't influence which setting is chosen."""
    full = tiny_dataset(tmp_path)
    without_held_out = full.model_copy(update={"items": full.tuning_items()})

    with_them = evaluate(full, tmp_path, with_chunk_sweep=True)
    without_them = evaluate(without_held_out, tmp_path, with_chunk_sweep=True)

    for key in ("counts", "ranking", "follow_ups_raw", "follow_ups_standalone", "top_scores",
                "threshold_sweep", "top_k_sweep", "alnum_sweep", "chunk_sweep"):
        assert with_them[key] == without_them[key], key
    # ...while the held-out item is still reported, on its own.
    assert with_them["held_out_counts"] == {"answerable": 1}
    assert with_them["ranking_held_out"].n == 1
    assert without_them["ranking_held_out"] is None


ORIGINAL_KEYS = ("counts", "held_out_counts", "ranking", "ranking_held_out", "follow_ups_raw",
                 "follow_ups_standalone", "top_scores", "top_scores_held_out", "threshold_sweep",
                 "top_k_sweep", "at_settings_held_out", "alnum_sweep")


def test_reworded_questions_never_change_the_original_results(tmp_path):
    plain = tiny_dataset(tmp_path)
    reworded = plain.model_validate({
        **plain.model_dump(),
        "reworded": [{"id": "rw-a1", "of": "a1", "question": "What does a mutation bring?",
                      "source": "claude"}],
    })

    without = evaluate(plain, tmp_path, with_chunk_sweep=False)
    with_them = evaluate(reworded, tmp_path, with_chunk_sweep=False)

    for key in ORIGINAL_KEYS:
        assert with_them[key] == without[key], key
    # ...and they are reported in their own set.
    assert [c.item_id for c in with_them["reworded_cases"]] == ["rw-a1"]
    assert with_them["front_matter"]["reworded"]["off"]["cutoff"].expected_kept.total == 1


def test_flagged_chunks_are_audited_but_their_text_stays_out_of_the_report(tmp_path):
    dataset = make_dataset(tmp_path, [answerable(pages=[1], evidence=["adds variety"])],
                           pages=[GA + " " + MUTATION, CONTENTS])
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    out = tmp_path / "results"

    main(args(tmp_path, out))

    report = (out / "retrieval-report.md").read_text(encoding="utf-8")
    audit = (out / "front-matter-audit.md").read_text(encoding="utf-8")
    (json_file,) = out.glob("retrieval-*.json")
    assert "1 chunks flagged" in report and "| ga | 1 | 2 |" in report
    assert "TABLE OF CONTENTS" in audit  # the audit shows the text, for a person to check
    assert "TABLE OF CONTENTS" not in report  # the committed report never does
    assert "TABLE OF CONTENTS" not in json_file.read_text(encoding="utf-8")
