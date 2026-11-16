import { MemoryRouter } from "react-router-dom";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import { OperationsPage } from "./operations";

it("requires confirmation then runs seed with explicit arguments and displays job output", async () => {
  const job = {
    id: "job1",
    command: "seed",
    args: ["--dry-run"],
    status: "completed",
    output: "Found 3 sources",
    exit_code: 0,
    created_at: 1,
    finished_at: 2,
    interactive: true,
    truncated: false,
  };
  let started = false;
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/commands")
        return new Response(
          JSON.stringify({
            commands: [
              {
                name: "seed",
                description: "Distill existing chats into memory",
                group: "Memory",
                interactive: true,
                confirmation: true,
                example: ["--dry-run"],
              },
            ],
          }),
        );
      if (url === "/api/jobs" && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          command: "seed",
          args: ["--dry-run"],
          confirmed: true,
        });
        started = true;
        return new Response(JSON.stringify(job));
      }
      if (url === "/api/jobs")
        return new Response(JSON.stringify({ jobs: started ? [job] : [] }));
      throw new Error(url);
    },
  );
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><OperationsPage /></MemoryRouter>);
  await screen.findByRole("button", { name: "Start command" });
  fireEvent.change(screen.getByLabelText("Arguments"), {
    target: { value: "--dry-run" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Start command" }));
  await screen.findByRole("dialog");
  expect(started).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Run command" }));
  await screen.findByText("Found 3 sources");
  expect(started).toBe(true);
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
});
