import { useId, useState } from "react";

import { getQuiz, MAX_QUIZ_QUESTIONS } from "../../api/study";
import type { QuizQuestion, QuizResponse } from "../../api/types";
import { useRequest } from "../../lib/useRequest";
import { ErrorNotice } from "../common/ErrorNotice";
import { NotFoundNotice } from "../common/NotFoundNotice";
import { ItemSourceLink } from "./ItemSourceLink";
import { StudyForm, type StudyPanelProps } from "./StudyForm";

/** A multiple-choice quiz from the ticked documents. */
export function QuizPanel({ documentIds, disabled = false }: StudyPanelProps) {
  const { result, pending, failure, run, retry } = useRequest<QuizResponse>();

  return (
    <div className="space-y-4">
      <StudyForm
        buttonLabel="Make quiz"
        pending={pending}
        disabled={disabled}
        count={{ label: "Questions", initial: 5, max: MAX_QUIZ_QUESTIONS }}
        onGenerate={(topic, numQuestions) =>
          void run(() => getQuiz({ documentIds, topic, numQuestions }))
        }
      />
      {pending && (
        <p role="status" className="text-sm text-gray-500">
          Writing questions…
        </p>
      )}
      {failure && <ErrorNotice key={failure.id} error={failure.error} onRetry={retry} />}
      {result && !result.found && <NotFoundNotice message={result.message ?? undefined} />}
      {/* A new quiz replaces this component (the result is cleared first), so answers reset. */}
      {result?.found && <Quiz questions={result.questions} />}
    </div>
  );
}

/** The questions and, once all are checked, the score. */
function Quiz({ questions }: { questions: QuizQuestion[] }) {
  // One entry per question: null until checked, then whether the answer was right.
  const [results, setResults] = useState<(boolean | null)[]>(() => questions.map(() => null));

  function recordResult(index: number, correct: boolean): void {
    setResults((previous) => previous.map((value, i) => (i === index ? correct : value)));
  }

  const allChecked = results.every((value) => value !== null);
  const score = results.filter((value) => value === true).length;

  return (
    <div className="space-y-4">
      {questions.map((question, index) => (
        <QuestionCard
          key={index}
          number={index + 1}
          question={question}
          onChecked={(correct) => recordResult(index, correct)}
        />
      ))}
      {allChecked && (
        <p className="text-lg font-semibold">
          Score: {score} of {questions.length}
        </p>
      )}
    </div>
  );
}

interface QuestionCardProps {
  number: number;
  question: QuizQuestion;
  onChecked: (correct: boolean) => void;
}

/** One question: pick an option, check it, then see the answer, explanation and source. */
function QuestionCard({ number, question, onChecked }: QuestionCardProps) {
  const [choice, setChoice] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);
  const groupName = useId(); // radio buttons of one question share a name

  function check(): void {
    if (choice === null) {
      return;
    }
    setChecked(true);
    onChecked(choice === question.correct_index);
  }

  const correct = choice === question.correct_index;

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm">
      {/* A disabled fieldset locks every option once the answer is checked. */}
      <fieldset disabled={checked} className="space-y-2">
        <legend className="mb-2 font-medium">
          {number}. {question.question}
        </legend>
        {question.options.map((option, i) => {
          const isCorrect = checked && i === question.correct_index;
          const isWrongChoice = checked && i === choice && !correct;
          return (
            <label
              key={i}
              className={`flex items-start gap-2 rounded p-1 ${
                isCorrect ? "bg-green-50" : isWrongChoice ? "bg-red-50" : ""
              }`}
            >
              <input
                type="radio"
                name={groupName}
                className="mt-1"
                checked={choice === i}
                onChange={() => setChoice(i)}
              />
              <span>
                {option}
                {isCorrect && <span className="ml-1 text-green-800">✓ (correct answer)</span>}
                {isWrongChoice && <span className="ml-1 text-red-800">✗ (your answer)</span>}
              </span>
            </label>
          );
        })}
      </fieldset>

      {!checked ? (
        <button
          type="button"
          disabled={choice === null}
          onClick={check}
          className="mt-3 rounded border border-blue-700 px-3 py-1 text-blue-700 disabled:opacity-50"
        >
          Check answer
        </button>
      ) : (
        <div className="mt-3 space-y-1">
          <p className={`font-medium ${correct ? "text-green-800" : "text-red-800"}`}>
            {correct ? "Correct!" : "Not quite."}
          </p>
          <p>{question.explanation}</p>
          <ItemSourceLink source={question.source} />
        </div>
      )}
    </div>
  );
}
