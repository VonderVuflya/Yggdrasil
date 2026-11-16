import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { Project } from "../lib/types";
import { Projects } from "./projects";
it("filters projects and retains project scope in knowledge links", async () => {
  const projects: Project[] = [
    {
      name: "Alpha",
      count: 8,
      archived_count: 0,
      latest_at: 1700000000,
      types: { decision: 8 },
    },
    {
      name: "Beta",
      count: 2,
      archived_count: 1,
      latest_at: 1700000000,
      types: { lesson: 2 },
    },
  ];
  render(
    <MemoryRouter>
      <Projects projects={projects} loading={false} error="" reload={vi.fn()} />
    </MemoryRouter>,
  );
  await userEvent.type(screen.getByLabelText("Find a project"), "Alpha");
  expect(
    screen.getByRole("link", { name: "Open project Alpha" }),
  ).toHaveAttribute("href", "/project?project=Alpha&tab=overview");
  expect(
    screen.queryByRole("link", { name: "Open project Beta" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Browse knowledge in Alpha" }),
  ).toHaveAttribute("href", "/project?project=Alpha&tab=knowledge");
});
