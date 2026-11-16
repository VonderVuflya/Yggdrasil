import { describe, it, expect, vi } from "vitest";
import { request, readEvents, establishSession } from "./api";
describe("API boundary", () => {
  it("sends same-origin credentials and CSRF header with scope unchanged", async () => {
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response('{"items":[]}'));
    await request("/api/memories", { project: "" });
    const options = fetcher.mock.calls[0][1]!;
    expect(options.credentials).toBe("same-origin");
    expect(options.headers).toMatchObject({ "X-Ygg-Request": "1" });
    expect(JSON.parse(options.body as string)).toEqual({ project: "" });
  });
  it("reports server errors rather than treating error payload as data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"error":"Сессия истекла"}', { status: 401 }),
    );
    await expect(request("/api/projects")).rejects.toThrow("Сессия истекла");
  });
  it("decodes events split across byte boundaries, including a final line without newline", async () => {
    const bytes = new TextEncoder().encode(
      '{"type":"delta","text":"Привет"}\n{"type":"done"}',
    );
    const stream = new ReadableStream({
      start(c) {
        c.enqueue(bytes.slice(0, 29));
        c.enqueue(bytes.slice(29));
        c.close();
      },
    });
    const result = [];
    for await (const event of readEvents(new Response(stream)))
      result.push(event);
    expect(result).toEqual([
      { type: "delta", text: "Привет" },
      { type: "done" },
    ]);
  });
  it("removes the launch ticket before sending it and does not erase query routing", async () => {
    window.history.replaceState(null, "", "/?project=Alpha#ticket=single-use");
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => {
        expect(window.location.hash).toBe("");
        return new Response("{}");
      });
    await establishSession();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe("?project=Alpha");
  });
});
