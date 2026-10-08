import { describe, expect, it, vi } from "vitest";

import { deleteConversation, getConversation, listConversations } from "./conversations";

function mockFetch(body: string | null, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("conversations API", () => {
  it("lists conversations", async () => {
    const fetchMock = mockFetch("[]");

    await expect(listConversations()).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations", undefined);
  });

  it("gets one conversation by its encoded id", async () => {
    const fetchMock = mockFetch('{"id":"c 1","title":"t","created_at":"x","messages":[]}');

    await getConversation("c 1");

    expect(fetchMock).toHaveBeenCalledWith("/api/conversations/c%201", undefined);
  });

  it("deletes a conversation", async () => {
    const fetchMock = mockFetch(null, 204);

    await expect(deleteConversation("c1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations/c1", { method: "DELETE" });
  });
});
