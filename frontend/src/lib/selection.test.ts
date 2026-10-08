import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DocumentInfo } from "../api/types";
import { loadSelection, moveSelection, saveSelection, useSelection } from "./selection";

function doc(id: string): DocumentInfo {
  return { id, filename: `${id}.pdf`, page_count: 1, chunk_count: 1, created_at: "2026-10-08T10:00:00" };
}

describe("loadSelection / saveSelection", () => {
  it("round-trips the ids for a conversation", () => {
    saveSelection("c1", ["d1", "d2"]);

    expect(loadSelection("c1")).toEqual(["d1", "d2"]);
  });

  it("keeps each conversation's selection separate", () => {
    saveSelection("c1", ["d1"]);
    saveSelection("c2", ["d2"]);

    expect(loadSelection("c1")).toEqual(["d1"]);
    expect(loadSelection("c2")).toEqual(["d2"]);
    expect(loadSelection("c3")).toEqual([]);
  });

  it("returns an empty selection for corrupt data", () => {
    localStorage.setItem("studymate.selection.c1", "{not json");
    localStorage.setItem("studymate.selection.c2", '{"d1": true}');
    localStorage.setItem("studymate.selection.c3", '["d1", 42]');

    expect(loadSelection("c1")).toEqual([]);
    expect(loadSelection("c2")).toEqual([]);
    expect(loadSelection("c3")).toEqual(["d1"]);
  });

  it("does not crash when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(() => saveSelection("c1", ["d1"])).not.toThrow();
    expect(loadSelection("c1")).toEqual([]);
  });
});

describe("moveSelection", () => {
  it("moves the ids to the new key and clears the old one", () => {
    saveSelection("new", ["d1"]);

    moveSelection("new", "c9");

    expect(loadSelection("c9")).toEqual(["d1"]);
    expect(loadSelection("new")).toEqual([]);
  });
});

describe("useSelection", () => {
  it("starts from storage and saves every change", () => {
    saveSelection("c1", ["d1"]);
    const { result } = renderHook(() => useSelection("c1", [doc("d1"), doc("d2")]));

    expect(result.current[0]).toEqual(["d1"]);
    act(() => result.current[1](["d1", "d2"]));

    expect(result.current[0]).toEqual(["d1", "d2"]);
    expect(loadSelection("c1")).toEqual(["d1", "d2"]);
  });

  it("hides ids of documents that no longer exist", () => {
    saveSelection("c1", ["d1", "gone"]);
    const { result } = renderHook(() => useSelection("c1", [doc("d1")]));

    expect(result.current[0]).toEqual(["d1"]);
  });

  it("keeps every id while the document list has not loaded", () => {
    saveSelection("c1", ["d1", "d2"]);
    const { result } = renderHook(() => useSelection("c1", null));

    expect(result.current[0]).toEqual(["d1", "d2"]);
  });

  it("loads the other conversation's selection when the key changes", () => {
    saveSelection("c1", ["d1"]);
    saveSelection("c2", ["d2"]);
    const docs = [doc("d1"), doc("d2")];
    const { result, rerender } = renderHook(({ key }) => useSelection(key, docs), {
      initialProps: { key: "c1" },
    });

    rerender({ key: "c2" });

    expect(result.current[0]).toEqual(["d2"]);
  });
});
