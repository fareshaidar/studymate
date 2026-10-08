import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type DocumentInfo } from "../../api/types";
import { uploadDocument, type UploadProgress } from "../../api/upload";
import { UploadDropzone } from "./UploadDropzone";

// Replace the real XHR upload with a mock each test controls by hand.
vi.mock("../../api/upload", () => ({ uploadDocument: vi.fn() }));

const pdf = new File(["%PDF-1.7"], "notes.pdf", { type: "application/pdf" });
const doc: DocumentInfo = {
  id: "d1",
  filename: "notes.pdf",
  page_count: 3,
  chunk_count: 9,
  created_at: "2026-10-08T10:00:00",
};

/**
 * Make the next upload wait until the test reports progress and then
 * resolves or rejects it, so the in-between states can be checked.
 */
function controlUpload() {
  let report: (progress: UploadProgress) => void = () => {};
  let finish: (value: DocumentInfo) => void = () => {};
  let fail: (error: unknown) => void = () => {};
  vi.mocked(uploadDocument).mockImplementation((_file, onProgress) => {
    report = onProgress;
    return new Promise((resolve, reject) => {
      finish = resolve;
      fail = reject;
    });
  });
  return {
    progress: (p: UploadProgress) => act(() => report(p)),
    resolve: () => act(async () => finish(doc)),
    reject: (error: unknown) => act(async () => fail(error)),
  };
}

beforeEach(() => {
  vi.mocked(uploadDocument).mockReset();
});

describe("UploadDropzone", () => {
  it("shows the upload percentage, then indexing, then calls onUploaded", async () => {
    const upload = controlUpload();
    const onUploaded = vi.fn();
    render(<UploadDropzone onUploaded={onUploaded} />);

    await userEvent.upload(screen.getByLabelText("Choose a PDF file"), pdf);
    upload.progress({ phase: "uploading", loaded: 42, total: 100 });
    expect(screen.getByText("Uploading… 42%")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload progress")).toHaveAttribute("value", "42");

    upload.progress({ phase: "indexing" });
    expect(screen.getByRole("status")).toHaveTextContent("Indexing…");

    await upload.resolve();
    expect(onUploaded).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("disables the picker while an upload is running", async () => {
    const upload = controlUpload();
    render(<UploadDropzone onUploaded={vi.fn()} />);
    const input = screen.getByLabelText("Choose a PDF file");

    await userEvent.upload(input, pdf);
    expect(input).toBeDisabled();

    await upload.resolve();
    expect(input).toBeEnabled();
  });

  it("shows the backend's message when the upload fails", async () => {
    const upload = controlUpload();
    const onUploaded = vi.fn();
    render(<UploadDropzone onUploaded={onUploaded} />);

    await userEvent.upload(screen.getByLabelText("Choose a PDF file"), pdf);
    await upload.reject(new ApiError(413, "File is larger than 50 MB."));

    expect(screen.getByRole("alert")).toHaveTextContent("File is larger than 50 MB.");
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("uploads a dropped PDF", async () => {
    const upload = controlUpload();
    render(<UploadDropzone onUploaded={vi.fn()} />);

    fireEvent.drop(screen.getByText(/Drop a PDF here/), { dataTransfer: { files: [pdf] } });

    expect(uploadDocument).toHaveBeenCalledWith(pdf, expect.any(Function));
    await upload.resolve();
  });

  it("rejects a dropped non-PDF without uploading it", () => {
    render(<UploadDropzone onUploaded={vi.fn()} />);
    const txt = new File(["hello"], "notes.txt", { type: "text/plain" });

    fireEvent.drop(screen.getByText(/Drop a PDF here/), { dataTransfer: { files: [txt] } });

    expect(screen.getByRole("alert")).toHaveTextContent("Only PDF files are supported.");
    expect(uploadDocument).not.toHaveBeenCalled();
  });
});
