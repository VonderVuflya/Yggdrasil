import { expect, it } from "vitest";
import { parseArguments } from "./arguments";
it("preserves quoted paths without executing substitutions", () => {
  expect(
    parseArguments("--source \"/tmp/my folder\" --project 'hello world' $(id)"),
  ).toEqual([
    "--source",
    "/tmp/my folder",
    "--project",
    "hello world",
    "$(id)",
  ]);
});
it("rejects unfinished quotes and retains empty args", () => {
  expect(() => parseArguments('"oops')).toThrow();
  expect(parseArguments('--content ""')).toEqual(["--content", ""]);
});
