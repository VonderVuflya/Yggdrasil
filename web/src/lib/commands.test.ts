import { expect, it } from "vitest";
import { commandGroups, groupedCommands, type Command } from "./commands";
const command = (name: string): Command => ({
  name,
  description: `Description for ${name}`,
  group: "raw",
  interactive: false,
  confirmation: false,
  example: [],
});
it("curates common tasks and excludes CLI-only commands and aliases even in advanced mode", () => {
  const names = commandGroups.flatMap((group) => [
    ...group.primary,
    ...group.advanced,
  ]);
  const excluded = [
    "ui",
    "serve",
    "mcp",
    "mcp-http",
    "token",
    "ensure",
    "wizard",
    "hw",
    "--help",
    "-h",
    "-help",
    "--version",
    "-V",
    "config",
    "update",
  ];
  const catalog = [...names, ...excluded].map(command);
  expect(new Set(names).size).toBe(names.length);
  const common = groupedCommands(catalog, false).flatMap((group) =>
    group.commands.map((item) => item.name),
  );
  expect(common).toHaveLength(14);
  expect(common).toContain("seed");
  expect(common).not.toContain("delete");
  const advanced = groupedCommands(catalog, true).flatMap((group) =>
    group.commands.map((item) => item.name),
  );
  expect(advanced).toContain("delete");
  expect(advanced).toContain("hooks");
  for (const name of excluded) expect(advanced).not.toContain(name);
});
it("only offers commands supplied by the server and omits empty groups", () => {
  const groups = groupedCommands([command("doctor")], false);
  expect(groups).toHaveLength(1);
  expect(groups[0].label).toBe("Inspect & search");
  expect(groups[0].commands[0].name).toBe("doctor");
});
