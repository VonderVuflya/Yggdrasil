import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
const project = {
  name: "Atlas",
  count: 3,
  archived_count: 0,
  latest_at: 1794823200,
  types: { decision: 3 },
};
afterEach(() => vi.unstubAllGlobals());
for (const tab of ["overview", "graph", "chat"])
  it(`hides experimental graph/chat UI even for a ${tab} project deep link`, async () => {
    const requested: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) => {
        const path = String(input);
        requested.push(path);
        const body =
          path === "/api/projects"
            ? { projects: [project] }
            : path === "/api/memories"
              ? { items: [], total: 0 }
              : {
                  current: "0.18.0",
                  running: "0.18.0",
                  available: false,
                  stars: null,
                  update: null,
                };
        return new Response(JSON.stringify(body));
      }),
    );
    render(
      <MemoryRouter initialEntries={[`/project?project=Atlas&tab=${tab}`]}>
        <App status={{ engine: true, user_id: "Demo", namespace: "demo" }} />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Atlas" });
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Knowledge",
      "Sources",
    ]);
    expect(
      screen.queryByRole("link", { name: "Global chat" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Ask about this project" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Explore graph")).not.toBeInTheDocument();
    expect(screen.getByText(/UI 0.1/)).toHaveTextContent("Experimental");
    await waitFor(() => expect(requested).toContain("/api/memories"));
    expect(requested.some((path) => /graph|chats/.test(path))).toBe(false);
  });
it("redirects the hidden global chat route to projects", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (input) =>
        new Response(
          JSON.stringify(
            String(input) === "/api/projects"
              ? { projects: [project] }
              : { current: "0.18.0", available: false, update: null },
          ),
        ),
    ),
  );
  render(
    <MemoryRouter initialEntries={["/chat"]}>
      <App status={{ engine: true, user_id: "Demo", namespace: "demo" }} />
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: /Everything you know/ });
  expect(
    screen.queryByRole("link", { name: /Ask across/ }),
  ).not.toBeInTheDocument();
});
