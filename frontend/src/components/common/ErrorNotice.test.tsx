import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/types";
import { ErrorNotice } from "./ErrorNotice";

afterEach(() => {
  vi.useRealTimers();
});

describe("ErrorNotice", () => {
  it("counts down a 503's Retry-After before enabling Retry", () => {
    vi.useFakeTimers();
    const onRetry = vi.fn();
    render(<ErrorNotice error={new ApiError(503, "The model is busy.", 2)} onRetry={onRetry} />);

    expect(screen.getByText("The model is busy.")).toBeInTheDocument();
    expect(screen.getByText("Busy: try again in 2 s.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled();

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("Busy: try again in 1 s.")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByText(/try again in/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers Retry straight away on a 502", () => {
    const onRetry = vi.fn();
    render(<ErrorNotice error={new ApiError(502, "The AI service failed.")} onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers a new chat instead of Retry on a 404", () => {
    const onNewChat = vi.fn();
    render(
      <ErrorNotice
        error={new ApiError(404, "Conversation not found.")}
        onRetry={vi.fn()}
        onNewChat={onNewChat}
      />,
    );

    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start a new chat" }));
    expect(onNewChat).toHaveBeenCalledTimes(1);
  });

  it("offers no Retry for a 422", () => {
    render(<ErrorNotice error={new ApiError(422, "question: too long")} onRetry={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("question: too long");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
