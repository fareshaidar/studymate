import json

import pytest

from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore
from app.services.chat import retrieve
from evaluation.harness import BACKEND_DATA_DIR, EvalIndex, UnsafePathError
from evaluation.metrics import kept_chunks
from evaluation.run_retrieval_eval import main, rank
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
        "tuned and reported on the same",
    ):
        assert heading in report
    assert "| held-out (owner-written) | 1 |" in report
    assert "| all (tuning set) | 3 |" in report  # 2 answerable + 1 follow-up
    (json_file,) = out.glob("retrieval-*.json")
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["counts"] == {
        "answerable": 2,
        "follow_up": 1,
        "unanswerable_off_topic": 1,
        "unanswerable_on_topic": 1,
    }
    a1 = next(c for c in data["cases"] if c["item_id"] == "a1")
    assert a1["ranking"][0]["page"] == ["ga", 1]  # the mutation page ranks first
    # No document text in the results.
    assert all("text" not in r for case in data["cases"] for r in case["ranking"])


def test_output_inside_backend_data_is_refused(tmp_path):
    dataset = tiny_dataset(tmp_path)
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    target = BACKEND_DATA_DIR / "eval-results-test"

    with pytest.raises(UnsafePathError):
        main(args(tmp_path, target))
    assert not target.exists()
