"""The evaluation dataset: questions, their ground truth, and the documents they are about.

The PDFs themselves are not in git. Each document entry names its file and its
SHA-256, so the evaluation can refuse to run on a different version of a file
(the expected pages would no longer be right).
"""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

EVAL_DIR = Path(__file__).parent
DEFAULT_DATASET = EVAL_DIR / "datasets" / "studymate_eval.json"
# Git-ignored. Every runner takes --documents to read the PDFs from somewhere else.
DEFAULT_DOCUMENTS_DIR = EVAL_DIR / "datasets" / "documents"

QuestionType = Literal[
    "answerable", "unanswerable_off_topic", "unanswerable_on_topic", "follow_up"
]
# Questions written by the project owner are kept apart as a held-out subset: they are
# never used to choose settings, so only they give an unbiased check of the chosen ones.
Author = Literal["claude", "user"]
HELD_OUT_AUTHOR = "user"

Text = Annotated[str, Field(min_length=1)]  # a non-empty string


class DocumentInfo(BaseModel):
    id: Text  # short name used by the items, e.g. "skylab"
    file: Text  # file name inside the documents folder
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: Text
    source: Text  # where the file came from
    licence: Text
    # The page ranges questions were written from (pages with readable text).
    question_pages: Text


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Text


class EvalItem(BaseModel):
    id: Text
    type: QuestionType
    question: Text
    author: Author = "claude"
    reference_answer: Text  # for unanswerable items: why it isn't in the documents
    # Answerable and follow-up items only:
    document: str | None = None
    pages: list[int] = []  # any page that really contains the answer counts
    # Short quotes copied from the PDF; every listed page must contain at least one.
    evidence: list[Text] = []
    # Follow-up items only:
    history: list[Turn] = []
    expected_standalone: str | None = None

    @model_validator(mode="after")
    def check_fields_for_type(self) -> "EvalItem":
        has_answer = self.type in ("answerable", "follow_up")
        if has_answer and not (self.document and self.pages and self.evidence):
            raise ValueError(f"{self.type} items need document, pages and evidence")
        if not has_answer and (self.document or self.pages or self.evidence):
            raise ValueError("unanswerable items must not have document, pages or evidence")
        if any(p < 1 for p in self.pages):
            raise ValueError("pages start at 1")
        is_follow_up = self.type == "follow_up"
        if is_follow_up and not (self.history and self.expected_standalone):
            raise ValueError("follow_up items need history and expected_standalone")
        if not is_follow_up and (self.history or self.expected_standalone):
            raise ValueError("only follow_up items have history or expected_standalone")
        return self


class EvalDataset(BaseModel):
    documents: list[DocumentInfo] = Field(min_length=1)
    items: list[EvalItem] = Field(min_length=1)

    @model_validator(mode="after")
    def check_references(self) -> "EvalDataset":
        doc_ids = [d.id for d in self.documents]
        item_ids = [i.id for i in self.items]
        for kind, ids in (("document", doc_ids), ("item", item_ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} ids: {duplicates}")
        for item in self.items:
            if item.document is not None and item.document not in doc_ids:
                raise ValueError(f"item {item.id}: unknown document {item.document!r}")
        return self

    def document(self, doc_id: str) -> DocumentInfo:
        return next(d for d in self.documents if d.id == doc_id)

    def held_out_ids(self) -> set[str]:
        """Ids of the owner-written items: reported on their own, never used for tuning."""
        return {i.id for i in self.items if i.author == HELD_OUT_AUTHOR}

    def tuning_items(self) -> list[EvalItem]:
        """The items sweeps and "tuning set" rows are computed from."""
        return [i for i in self.items if i.author != HELD_OUT_AUTHOR]


def load_dataset(path: Path = DEFAULT_DATASET) -> EvalDataset:
    """Read and validate the dataset file (raises pydantic.ValidationError if it's wrong)."""
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class DocumentFileError(Exception):
    """A document's PDF is missing or isn't the exact file the dataset was written from."""


def document_path(doc: DocumentInfo, documents_dir: Path) -> Path:
    """The PDF of `doc`, after checking it exists and is byte-for-byte the expected file."""
    path = documents_dir / doc.file
    if not path.is_file():
        raise DocumentFileError(f"{doc.id}: {path} not found (set --documents to its folder)")
    if sha256_of(path) != doc.sha256:
        raise DocumentFileError(f"{doc.id}: {path} is not the file the dataset was written from")
    return path
