import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getHealth } from "../../api/documents";
import { ApiError } from "../../api/types";
import { BackendStatus, HEALTH_CHECK_MS } from "./BackendStatus";

vi.mock("../../api/documents", () => ({ getHealth: vi.fn() }));

const down = () => Promise.reject(new ApiError(0, "offline"));
const up = () => Promise.resolve({ status: "ok" });

/** Let pending promises (the health check) settle inside act. */
async function settle(): Promise<void> {
  await act(async () => {});
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getHealth).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("BackendStatus", () => {
  it("shows nothing while the backend answers", async () => {
    vi.mocked(getHealth).mockImplementation(up);

    render(<BackendStatus />);
    await settle();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("re-checks every 30 s and reports when the backend is back", async () => {
    vi.mocked(getHealth).mockImplementation(down);
    const onBackOnline = vi.fn();
    render(<BackendStatus onBackOnline={onBackOnline} />);
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("not responding");

    vi.mocked(getHealth).mockImplementation(up);
    await act(async () => vi.advanceTimersByTime(HEALTH_CHECK_MS));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onBackOnline).toHaveBeenCalledTimes(1);
  });

  it("does not call onBackOnline when it was never offline", async () => {
    vi.mocked(getHealth).mockImplementation(up);
    const onBackOnline = vi.fn();
    render(<BackendStatus onBackOnline={onBackOnline} />);
    await settle();

    await act(async () => vi.advanceTimersByTime(HEALTH_CHECK_MS));

    expect(onBackOnline).not.toHaveBeenCalled();
  });

  it("checks immediately with Check now", async () => {
    vi.mocked(getHealth).mockImplementation(down);
    render(<BackendStatus />);
    await settle();

    vi.mocked(getHealth).mockImplementation(up);
    fireEvent.click(screen.getByRole("button", { name: "Check now" }));
    await settle();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("warns about a missing API key until a re-check finds one", async () => {
    vi.mocked(getHealth).mockResolvedValue({ status: "ok", llm_configured: false });
    render(<BackendStatus />);
    await settle();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The AI isn't set up yet: add GEMINI_API_KEY=<your key> to backend/.env, then restart " +
        "the backend. Uploading and browsing still work; questions and study tools need the key.",
    );

    // The backend was restarted with a key.
    vi.mocked(getHealth).mockResolvedValue({ status: "ok", llm_configured: true });
    await act(async () => vi.advanceTimersByTime(HEALTH_CHECK_MS));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("raises no key warning when an older backend doesn't send llm_configured", async () => {
    vi.mocked(getHealth).mockResolvedValue({ status: "ok" });

    render(<BackendStatus />);
    await settle();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the offline banner, not the key warning, when the backend is down", async () => {
    vi.mocked(getHealth).mockResolvedValue({ status: "ok", llm_configured: false });
    render(<BackendStatus />);
    await settle();

    vi.mocked(getHealth).mockImplementation(down);
    fireEvent.click(screen.getByRole("button", { name: "Check now" }));
    await settle();

    expect(screen.getByRole("alert")).toHaveTextContent("not responding");
    expect(screen.queryByText(/isn't set up yet/)).not.toBeInTheDocument();
  });

  it("checks when the browser tab regains focus", async () => {
    vi.mocked(getHealth).mockImplementation(up);
    render(<BackendStatus />);
    await settle();
    expect(getHealth).toHaveBeenCalledTimes(1);

    vi.mocked(getHealth).mockImplementation(down);
    fireEvent.focus(window);
    await settle();

    expect(getHealth).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
