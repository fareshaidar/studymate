import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MessageInput } from "./MessageInput";

/** MessageInput is controlled, so tests wrap it with real state, like ChatView does. */
function Harness({ onSend, disabled = false }: { onSend: (q: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState("");
  return <MessageInput value={value} onChange={setValue} onSend={onSend} disabled={disabled} />;
}

describe("MessageInput", () => {
  it("sends the trimmed question on Enter", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);

    await userEvent.type(screen.getByLabelText("Your question"), "  What is mitosis?  {Enter}");

    expect(onSend).toHaveBeenCalledWith("What is mitosis?");
  });

  it("adds a new line on Shift+Enter instead of sending", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    const box = screen.getByLabelText("Your question");

    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two");

    expect(onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("line one\nline two");
  });

  it("sends with the Send button too", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);

    await userEvent.type(screen.getByLabelText("Your question"), "Why?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(onSend).toHaveBeenCalledWith("Why?");
  });

  it("ignores an empty or blank question", async () => {
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);

    await userEvent.type(screen.getByLabelText("Your question"), "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("is disabled while waiting for an answer", () => {
    render(<Harness onSend={vi.fn()} disabled />);

    expect(screen.getByLabelText("Your question")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
