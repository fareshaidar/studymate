import { request } from "./client";
import type { FlashcardsResponse, QuizResponse, SummaryResponse } from "./types";

/** The backend's limits (StudyRequest, QuizRequest and FlashcardsRequest in api/study.py). */
export const MAX_TOPIC_CHARS = 200;
export const MAX_QUIZ_QUESTIONS = 10;
export const MAX_FLASHCARDS = 20;

export interface StudyInput {
  /** Ticked documents; empty means "use all documents". */
  documentIds: string[];
  /** Optional focus, e.g. "photosynthesis". Blank means the whole material. */
  topic: string;
}

/** The JSON body shared by the three study endpoints. */
function studyBody({ documentIds, topic }: StudyInput): Record<string, unknown> {
  const body: Record<string, unknown> = { document_ids: documentIds };
  const trimmed = topic.trim();
  if (trimmed) {
    body.topic = trimmed;
  }
  return body;
}

function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** POST /study/summary: a summary of the documents (or of one topic in them). */
export function getSummary(input: StudyInput): Promise<SummaryResponse> {
  return post<SummaryResponse>("/study/summary", studyBody(input));
}

/** POST /study/quiz: multiple-choice questions with sources. */
export function getQuiz(input: StudyInput & { numQuestions: number }): Promise<QuizResponse> {
  return post<QuizResponse>("/study/quiz", { ...studyBody(input), num_questions: input.numQuestions });
}

/** POST /study/flashcards: question/answer cards with sources. */
export function getFlashcards(input: StudyInput & { numCards: number }): Promise<FlashcardsResponse> {
  return post<FlashcardsResponse>("/study/flashcards", { ...studyBody(input), num_cards: input.numCards });
}
