import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/types";
import { useRequest } from "./useRequest";

describe("useRequest", () => {
  it("stores the result of a successful call", async () => {
    const { result } = renderHook(() => useRequest<string>());

    await act(() => result.current.run(() => Promise.resolve("summary")));

    expect(result.current.result).toBe("summary");
    expect(result.current.pending).toBe(false);
    expect(result.current.failure).toBeNull();
  });

  it("is pending while the call runs", async () => {
    let finish: (value: string) => void = () => {};
    const { result } = renderHook(() => useRequest<string>());

    act(() => void result.current.run(() => new Promise((resolve) => (finish = resolve))));
    expect(result.current.pending).toBe(true);

    await act(async () => finish("done"));
    expect(result.current.pending).toBe(false);
  });

  it("stores a failure, and retry runs the same call again", async () => {
    const call = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(502, "The AI service failed."))
      .mockResolvedValueOnce("summary");
    const { result } = renderHook(() => useRequest<string>());

    await act(() => result.current.run(call));
    expect(result.current.failure?.error.status).toBe(502);
    expect(result.current.result).toBeNull();

    await act(async () => result.current.retry());
    expect(call).toHaveBeenCalledTimes(2);
    expect(result.current.failure).toBeNull();
    expect(result.current.result).toBe("summary");
  });

  it("wraps an unexpected error as an ApiError", async () => {
    const { result } = renderHook(() => useRequest<string>());

    await act(() => result.current.run(() => Promise.reject(new Error("boom"))));

    expect(result.current.failure?.error).toBeInstanceOf(ApiError);
    expect(result.current.failure?.error.message).toBe("Something went wrong.");
  });
});
