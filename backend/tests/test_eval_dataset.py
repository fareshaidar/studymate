import pytest
from pydantic import ValidationError

from evaluation.check_dataset import check_dataset, main, normalise, write_review
from evaluation.dataset import (
    DEFAULT_DATASET,
    DEFAULT_DOCUMENTS_DIR,
    DocumentFileError,
    EvalDataset,
    EvalItem,
    document_path,
    load_dataset,
    sha256_of,
)
from tests.helpers import make_pdf

PAGES = [
    "Mutation adds variety to the population.",
    "Selection keeps the fittest individuals.",
    "Mutation adds variety, as said before.",
]


def answerable(**overrides) -> dict:
    item = {
        "id": "a1",
        "type": "answerable",
        "question": "What does mutation add?",
        "reference_answer": "Variety.",
        "document": "ga",
        "pages": [1],
        "evidence": ["Mutation adds variety"],
    }
    return {**item, **overrides}


def make_dataset(tmp_path, items, pages=PAGES) -> EvalDataset:
    pdf = tmp_path / "ga.pdf"
    make_pdf(pdf, pages)
    document = {
        "id": "ga",
        "file": "ga.pdf",
        "sha256": sha256_of(pdf),
        "title": "GA notes",
        "source": "tests",
        "licence": "own",
        "question_pages": "1-3",
    }
    return EvalDataset.model_validate({"documents": [document], "items": items})


# --- schema ---


def test_valid_items_of_every_type():
    follow_up = answerable(
        id="f1",
        type="follow_up",
        question="And selection?",
        history=[{"role": "user", "content": "What does mutation add?"}],
        expected_standalone="What does selection do in a GA?",
    )
    off = {"id": "u1", "type": "unanswerable_off_topic", "question": "Pizza?", "reference_answer": "Not covered."}

    items = [EvalItem.model_validate(i) for i in (answerable(), follow_up, off)]

    assert items[0].author == "claude"
    assert items[1].history[0].role == "user"


@pytest.mark.parametrize(
    "item",
    [
        answerable(pages=[]),
        answerable(evidence=[]),
        answerable(document=None),
        answerable(pages=[0]),
        answerable(question=""),
        answerable(author="someone"),
        answerable(type="follow_up"),  # no history
        answerable(expected_standalone="What does mutation add in a GA?"),  # not a follow-up
        {"id": "u1", "type": "unanswerable_on_topic", "question": "Q?", "reference_answer": "No.", "pages": [1]},
    ],
)
def test_invalid_items_are_rejected(item):
    with pytest.raises(ValidationError):
        EvalItem.model_validate(item)


def test_duplicate_ids_and_unknown_documents_are_rejected(tmp_path):
    with pytest.raises(ValidationError, match="duplicate item ids"):
        make_dataset(tmp_path, [answerable(), answerable()])
    with pytest.raises(ValidationError, match="unknown document"):
        make_dataset(tmp_path, [answerable(document="nope")])


def test_document_path_checks_the_file(tmp_path):
    dataset = make_dataset(tmp_path, [answerable()])
    doc = dataset.documents[0]

    assert document_path(doc, tmp_path) == tmp_path / "ga.pdf"
    with pytest.raises(DocumentFileError, match="not found"):
        document_path(doc, tmp_path / "elsewhere")
    (tmp_path / "ga.pdf").write_bytes(b"changed")
    with pytest.raises(DocumentFileError, match="not the file"):
        document_path(doc, tmp_path)


# --- checker ---


def test_normalise_ignores_case_punctuation_and_line_breaks():
    assert normalise("Mutation  adds\nvariety, (really)!") == "mutation adds variety really"


def test_correct_evidence_passes_and_other_pages_are_suggested(tmp_path):
    dataset = make_dataset(tmp_path, [answerable()])

    result = check_dataset(dataset, tmp_path)

    assert result.problems == []
    assert result.maybe_also == {"a1": [3]}  # page 3 says the same thing


def test_each_page_needs_one_of_the_quotes(tmp_path):
    # The same answer worded differently on two pages: one quote per page is enough.
    item = answerable(pages=[1, 2], evidence=["adds variety to the population", "keeps the fittest"])
    dataset = make_dataset(tmp_path, [item])

    assert check_dataset(dataset, tmp_path).problems == []


def test_wrong_page_or_missing_page_is_a_problem(tmp_path):
    dataset = make_dataset(tmp_path, [answerable(pages=[2]), answerable(id="a2", pages=[9])])

    problems = check_dataset(dataset, tmp_path).problems

    assert problems == [
        "a1: no evidence quote found on page 2",
        "a2: page 9 doesn't exist or has no text",
    ]


def test_missing_file_is_a_problem(tmp_path):
    dataset = make_dataset(tmp_path, [answerable()])

    result = check_dataset(dataset, tmp_path / "elsewhere")

    assert len(result.problems) == 1 and "not found" in result.problems[0]


def test_review_sheet_shows_question_and_page_text(tmp_path):
    dataset = make_dataset(tmp_path, [answerable()])
    result = check_dataset(dataset, tmp_path)
    review = tmp_path / "out" / "review.md"

    write_review(dataset, result, review)

    text = review.read_text(encoding="utf-8")
    assert "## a1 (answerable, by claude)" in text
    assert "What does mutation add?" in text
    assert "Page 1: …Mutation adds variety to the population." in text
    assert "Maybe also on pages:** [3]" in text


def test_main_returns_1_on_problems(tmp_path):
    dataset = make_dataset(tmp_path, [answerable(pages=[2])])
    path = tmp_path / "dataset.json"
    path.write_text(dataset.model_dump_json(), encoding="utf-8")

    code = main(["--dataset", str(path), "--documents", str(tmp_path), "--review", str(tmp_path / "r.md")])

    assert code == 1


# --- the real dataset ---


def test_committed_dataset_is_valid():
    dataset = load_dataset(DEFAULT_DATASET)
    assert len(dataset.items) >= 40


def test_committed_dataset_matches_the_pdfs():
    dataset = load_dataset(DEFAULT_DATASET)
    if not all((DEFAULT_DOCUMENTS_DIR / d.file).exists() for d in dataset.documents):
        pytest.skip("the evaluation PDFs are not in the default documents folder (not in git)")
    assert check_dataset(dataset, DEFAULT_DOCUMENTS_DIR).problems == []
