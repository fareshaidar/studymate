import json

import pytest
from pydantic import ValidationError

from app.llm.errors import InvalidLLMOutputError, ProviderError
from app.rag.structured import (
    FlashcardsLLM,
    QuizLLM,
    generate_json,
    strip_code_fences,
)
from tests.fakes import FakeLLMClient


def quiz_item(**changes):
    item = {
        "question": "What does mutation add?",
        "options": ["Variety", "Speed", "Memory", "Nothing"],
        "correct_index": 0,
        "explanation": "Mutation adds variety to the population.",
        "passage": 1,
    }
    item.update(changes)
    return item


def quiz_json(*items):
    return json.dumps({"questions": list(items) or [quiz_item()]})


def parse_quiz(reply, n_passages=3):
    return QuizLLM.model_validate_json(strip_code_fences(reply), context={"n_passages": n_passages})


@pytest.mark.parametrize(
    "wrap",
    [
        lambda j: j,
        lambda j: f"```json\n{j}\n```",
        lambda j: f"```\n{j}\n```",
        lambda j: f"  ```JSON\n{j}```  \n",
    ],
)
def test_code_fences_are_tolerated(wrap):
    quiz = parse_quiz(wrap(quiz_json()))
    assert quiz.questions[0].options[0] == "Variety"


def test_valid_quiz_is_parsed_and_stripped():
    quiz = parse_quiz(quiz_json(quiz_item(question="  What does mutation add?  ", passage=3)))
    item = quiz.questions[0]
    assert item.question == "What does mutation add?"
    assert item.correct_index == 0
    assert item.passage == 3


@pytest.mark.parametrize(
    "bad",
    [
        quiz_item(options=["A", "B", "C"]),
        quiz_item(options=["A", "B", "C", "D", "E"]),
        quiz_item(options=["Variety", "Speed", "variety ", "Memory"]),
        quiz_item(options=["A", "B", "", "D"]),
        quiz_item(correct_index=4),
        quiz_item(correct_index=-1),
        quiz_item(passage=0),
        quiz_item(passage=4),
        quiz_item(question="   "),
    ],
    ids=[
        "3 options",
        "5 options",
        "duplicate options",
        "empty option",
        "index too high",
        "negative index",
        "passage 0",
        "passage not sent",
        "empty question",
    ],
)
def test_invalid_quiz_items_are_rejected(bad):
    with pytest.raises(ValidationError):
        parse_quiz(quiz_json(bad))


@pytest.mark.parametrize("reply", ["not json", '{"questions": []}', "[1, 2]", ""])
def test_invalid_json_or_shape_is_rejected(reply):
    with pytest.raises(ValidationError):
        parse_quiz(reply)


def test_flashcards_are_validated():
    cards = FlashcardsLLM.model_validate_json(
        '{"cards": [{"front": "Mutation?", "back": "Adds variety.", "passage": 2}]}',
        context={"n_passages": 2},
    )
    assert cards.cards[0].back == "Adds variety."
    with pytest.raises(ValidationError):
        FlashcardsLLM.model_validate_json(
            '{"cards": [{"front": "Mutation?", "back": "", "passage": 1}]}',
            context={"n_passages": 2},
        )


def ask(llm):
    return generate_json(
        llm, "PROMPT", system="SYSTEM", schema=QuizLLM, context={"n_passages": 3}
    )


def test_valid_reply_needs_one_call():
    llm = FakeLLMClient(replies=[quiz_json()])
    assert ask(llm).questions[0].question == "What does mutation add?"
    assert len(llm.calls) == 1
    assert llm.calls[0] == ("PROMPT", "SYSTEM")


def test_invalid_reply_is_retried_once_with_the_errors():
    llm = FakeLLMClient(replies=[quiz_json(quiz_item(correct_index=7)), quiz_json()])

    quiz = ask(llm)

    assert quiz.questions[0].correct_index == 0
    assert len(llm.calls) == 2
    retry_prompt, retry_system = llm.calls[1]
    assert retry_system == "SYSTEM"
    assert retry_prompt.startswith("PROMPT")
    assert "questions.0.correct_index" in retry_prompt
    assert "JSON only" in retry_prompt


def test_second_invalid_reply_raises_friendly_error(caplog):
    secret = "SECRET-GENERATED-TEXT"
    llm = FakeLLMClient(replies=[f"Sure! {secret}", f"```{secret}```"])

    with caplog.at_level("WARNING", logger="app.rag.structured"):
        with pytest.raises(InvalidLLMOutputError) as info:
            ask(llm)

    assert len(llm.calls) == 2
    assert info.value.user_message == InvalidLLMOutputError.user_message
    assert "study invalid_json attempt=1" in caplog.text
    assert "study invalid_json attempt=2" in caplog.text
    assert secret not in caplog.text
    assert secret not in str(info.value)


def test_llm_errors_are_not_retried_here():
    # Transient errors are already retried by the client; generate_json only retries bad JSON.
    llm = FakeLLMClient(replies=[ProviderError("boom", status_code=500), quiz_json()])
    with pytest.raises(ProviderError):
        ask(llm)
    assert len(llm.calls) == 1
