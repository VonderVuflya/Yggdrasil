import { afterEach, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { SettingsPage } from "./settings";
import { getTheme, setTheme } from "../lib/theme";
import { setLanguage } from "../lib/i18n";

afterEach(() => {
  act(() => {
    setTheme({ palette: "green", mode: "light" });
    setLanguage("en");
  });
  localStorage.clear();
});
it("offers all five palettes in settings and preserves the palette across mode changes", async () => {
  render(
    <MemoryRouter initialEntries={["/settings?section=appearance"]}>
      <SettingsPage />
    </MemoryRouter>,
  );
  expect(screen.getAllByRole("radio")).toHaveLength(7);
  const user = userEvent.setup();
  await user.click(screen.getByRole("radio", { name: "Blue" }));
  await user.click(screen.getByRole("radio", { name: "Dark" }));
  expect(screen.getByRole("radio", { name: "Blue" })).toBeChecked();
  expect(getTheme()).toEqual({ palette: "blue", mode: "dark" });
  expect(document.documentElement.dataset.palette).toBe("blue");
  const neutral = screen.getByRole("radio", { name: "Neutral" });
  neutral.focus();
  await user.keyboard(" ");
  expect(neutral).toBeChecked();
  expect(localStorage.getItem("ygg-palette")).toBe("neutral");
});
it("translates appearance controls without resetting the chosen colors", () => {
  act(() => {
    setTheme({ palette: "pink", mode: "dark" });
    setLanguage("ru");
  });
  render(
    <MemoryRouter initialEntries={["/settings?section=appearance"]}>
      <SettingsPage />
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("heading", { name: "Оформление" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Розовая" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Тёмный" })).toBeChecked();
});
