import { useEffect, useRef } from "react";

import type { Source } from "../../api/types";
import { AnswerMessage } from "./AnswerMessage";

/** One message on screen: the student's question or StudyMate's answer. */
export type ChatMessage =
  | { id: number; role: "user"; text: string }
  | {
      id: number;
      role: "assistant";
      answer: string;
      found: boolean;
      reason: string | null;
      sources: Source[];
      /** The standalone question used for the search, if the follow-up was rewritten. */
      rewrittenQuestion: string | null;
    };

interface MessageListProps {
  messages: ChatMessage[];
  /** True while waiting for an answer: shows the thinking indicator. */
  pending: boolean;
  /** Ids of documents that still exist; see SourceDetails. */
  existingDocumentIds?: Set<string>;
}

/** The conversation so far, scrolled to the newest message. */
export function MessageList({ messages, pending, existingDocumentIds }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Optional call: jsdom (tests) has no scrollIntoView.
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages.length, pending]);

  return (
    <div className="space-y-4">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.id} className="flex justify-end">
            <p className="max-w-[80%] rounded-lg bg-blue-700 px-3 py-2 whitespace-pre-wrap text-white">
              {message.text}
            </p>
          </div>
        ) : (
          <div key={message.id} className="max-w-[90%]">
            {message.rewrittenQuestion && (
              <p className="mb-1 text-xs text-gray-500">Searched as: {message.rewrittenQuestion}</p>
            )}
            <AnswerMessage
              answer={message.answer}
              found={message.found}
              reason={message.reason}
              sources={message.sources}
              existingDocumentIds={existingDocumentIds}
            />
          </div>
        ),
      )}
      {pending && (
        <p role="status" className="text-sm text-gray-500">
          StudyMate is thinking…
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
