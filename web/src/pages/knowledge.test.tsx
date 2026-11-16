import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Knowledge } from "./knowledge";
it("distinguishes all sources from records with no source", async () => {
  const requests: Record<string, unknown>[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    if (String(input) === "/api/sources")
      return new Response(
        '{"sources":[{"name":"","count":1},{"name":"notes.md","count":2}]}',
      );
    const body = JSON.parse(options?.body as string);
    requests.push(body);
    return new Response(JSON.stringify({ items: [], total: 0 }));
  });
  render(
    <Knowledge
      project={{
        name: "Alpha",
        count: 3,
        archived_count: 0,
        latest_at: 0,
        types: {},
      }}
      onSelect={() => {}}
    />,
  );
  await screen.findByText("No records found");
  expect(requests[0]).not.toHaveProperty("source");
  await userEvent.selectOptions(screen.getByLabelText("Source"), "");
  await vi.waitFor(() => expect(requests.at(-1)).toHaveProperty("source", ""));
});
