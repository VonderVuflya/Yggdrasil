import { render, screen, fireEvent } from "@testing-library/react";
import { beforeAll, expect, it, vi } from "vitest";
import { CommandSelect } from "./command-select";
// jsdom has no layout/scrolling API; Radix uses this for keyboard focus.
beforeAll(() => { Element.prototype.scrollIntoView = vi.fn(); });
const commands = [
  {
    name: "seed",
    description: "Distill existing chats into memory",
    group: "Memory",
    interactive: true,
    confirmation: true,
    example: ["--dry-run"],
  },
  {
    name: "doctor",
    description: "Diagnose the installation",
    group: "Diagnostics",
    interactive: false,
    confirmation: false,
    example: [],
  },
  {
    name: "delete",
    description: "Permanently delete a memory",
    group: "Memory",
    interactive: false,
    confirmation: true,
    example: [],
  },
];
it("groups options and shows each description while keeping advanced commands out of the default list", async () => {
  render(
    <CommandSelect
      commands={commands}
      value="seed"
      advanced={false}
      onChange={vi.fn()}
    />,
  );
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "ArrowDown" });
  expect(await screen.findByRole("listbox")).toBeInTheDocument();
  expect(screen.getByText("Import & sync")).toBeInTheDocument();
  expect(screen.getByText("Inspect & search")).toBeInTheDocument();
  expect(
    screen.getByText("Distill existing chats into memory"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: /delete/ }),
  ).not.toBeInTheDocument();
});
