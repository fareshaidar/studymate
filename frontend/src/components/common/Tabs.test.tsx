import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Tabs } from "./Tabs";

const TABS = [
  { id: "chat", label: "Chat" },
  { id: "study", label: "Study" },
  { id: "notes", label: "Notes" },
];

function Harness() {
  const [selected, setSelected] = useState("chat");
  return <Tabs label="Main view" tabs={TABS} selected={selected} onSelect={setSelected} idPrefix="main" />;
}

describe("Tabs", () => {
  it("puts only the selected tab in the Tab order", () => {
    render(<Harness />);

    expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Study" })).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute("aria-controls", "main-panel-chat");
  });

  it("moves selection and focus with the arrow keys, wrapping at the ends", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("tab", { name: "Chat" }));

    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Study" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Study" })).toHaveFocus();

    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Chat" })).toHaveFocus();

    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
  });

  it("jumps to the first and last tab with Home and End", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("tab", { name: "Study" }));

    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveFocus();

    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Chat" })).toHaveFocus();
  });
});
