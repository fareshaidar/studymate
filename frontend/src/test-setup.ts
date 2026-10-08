// Adds DOM assertions such as toBeInTheDocument() to Vitest's expect.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  // Remove rendered components and undo vi.stubGlobal so tests stay independent.
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
