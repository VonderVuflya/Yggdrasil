import { act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  getTheme,
  initializeTheme,
  palettes,
  savedTheme,
  setTheme,
  themeTokens,
} from "./theme";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  act(() => setTheme({ palette: "green", mode: "light" }));
  localStorage.clear();
});
it("preserves the existing dark-mode preference and validates saved palettes", () => {
  localStorage.clear();
  expect(savedTheme()).toEqual({ palette: "green", mode: "light" });
  localStorage.setItem("ygg-theme", "dark");
  localStorage.setItem("ygg-palette", "not-a-palette");
  expect(savedTheme()).toEqual({ palette: "green", mode: "dark" });
  localStorage.setItem("ygg-palette", "orange");
  initializeTheme();
  expect(document.documentElement.dataset.palette).toBe("orange");
  expect(document.documentElement).toHaveClass("dark");
  expect(document.documentElement.style.colorScheme).toBe("dark");
});
it("keeps the selected palette when switching mode, and restores both after reinitialization", () => {
  setTheme({ palette: "blue", mode: "dark" });
  setTheme({ mode: "light" });
  expect(getTheme()).toEqual({ palette: "blue", mode: "light" });
  expect(localStorage.getItem("ygg-theme")).toBe("light");
  expect(localStorage.getItem("ygg-palette")).toBe("blue");
  initializeTheme();
  expect(document.documentElement.dataset.palette).toBe("blue");
  expect(document.documentElement).not.toHaveClass("dark");
  expect(document.documentElement.style.getPropertyValue("--primary")).toBe(
    themeTokens(getTheme())["--primary"],
  );
});
it("synchronizes changes and storage clearing across tabs", () => {
  initializeTheme();
  localStorage.setItem("ygg-palette", "pink");
  localStorage.setItem("ygg-theme", "dark");
  window.dispatchEvent(new StorageEvent("storage", { key: "ygg-palette" }));
  expect(getTheme()).toEqual({ palette: "pink", mode: "dark" });
  localStorage.clear();
  window.dispatchEvent(new StorageEvent("storage", { key: null }));
  expect(getTheme()).toEqual({ palette: "green", mode: "light" });
});
it("still applies appearance and notifies the 3D graph when storage is unavailable", () => {
  const changed = vi.fn();
  window.addEventListener("ygg-theme-changed", changed);
  try {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setTheme({ palette: "neutral", mode: "dark" });
    expect(getTheme()).toEqual({ palette: "neutral", mode: "dark" });
    expect(changed).toHaveBeenCalledOnce();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(savedTheme()).toEqual({ palette: "green", mode: "light" });
  } finally {
    window.removeEventListener("ygg-theme-changed", changed);
  }
});
function luminance(hex: string) {
  const rgb = hex
    .slice(1)
    .match(/../g)!
    .map((v) => parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function contrast(a: string, b: string) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
for (const palette of palettes)
  for (const mode of ["light", "dark"] as const) {
    it(`${palette} ${mode} keeps text readable and controls visible`, () => {
      const tokens = themeTokens({ palette, mode });
      for (const background of [
        "--background",
        "--card",
        "--secondary",
        "--sidebar",
      ]) {
        for (const foreground of [
          "--foreground",
          "--muted-foreground",
          "--primary",
          "--destructive",
        ]) {
          expect(
            contrast(tokens[foreground], tokens[background]),
            `${foreground} on ${background}`,
          ).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(
        contrast(tokens["--primary"], tokens["--primary-foreground"]),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(tokens["--destructive"], tokens["--destructive-foreground"]),
      ).toBeGreaterThanOrEqual(4.5);
      for (const background of ["--background", "--card"]) {
        expect(
          contrast(tokens["--input"], tokens[background]),
          `input on ${background}`,
        ).toBeGreaterThanOrEqual(3);
      }
    });
  }
