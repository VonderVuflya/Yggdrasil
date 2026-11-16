import { afterEach, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import {
  catalogs,
  getLanguage,
  I18nProvider,
  LanguagePicker,
  languages,
  savedLanguage,
  setLanguage,
  translate,
  useI18n,
} from "./i18n";
import { Projects } from "../pages/projects";
import { date, typeName } from "./utils";
afterEach(() => {
  act(() => setLanguage("en"));
  localStorage.clear();
});
it("defaults to English and rejects unsupported persisted values", () => {
  localStorage.clear();
  expect(savedLanguage()).toBe("en");
  localStorage.setItem("ygg-language", "unsupported");
  expect(savedLanguage()).toBe("en");
  expect(getLanguage()).toBe("en");
});
it("provides complete catalogs with matching interpolation variables for all README languages", () => {
  expect(Object.keys(languages)).toEqual([
    "en",
    "ru",
    "de",
    "es",
    "fr",
    "ja",
    "zh",
  ]);
  const tokens = (value: string) => (value.match(/\{\w+\}/g) || []).sort();
  for (const catalog of Object.values(catalogs)) {
    expect(Object.keys(catalog).sort()).toEqual(
      Object.keys(catalogs.en).sort(),
    );
    for (const [key, value] of Object.entries(catalog)) {
      expect(value.trim(), key).not.toBe("");
      expect(tokens(value), key).toEqual(tokens(key));
    }
  }
});
it("changes visible chrome, persists the language and leaves project content untouched", async () => {
  const projects = [
    {
      name: "Сырой проект",
      count: 1500,
      archived_count: 0,
      latest_at: 1700000000,
      types: { decision: 1500 },
    },
  ];
  const content = (
    <I18nProvider>
      <LanguagePicker />
      <MemoryRouter>
        <Projects
          projects={projects}
          loading={false}
          error=""
          reload={vi.fn()}
        />
      </MemoryRouter>
    </I18nProvider>
  );
  const view = render(content);
  expect(screen.getByRole("button", { name: "Language" })).toHaveAttribute(
    "title",
    "English",
  );
  expect(
    screen.getByRole("heading", { name: /Everything you know/ }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Language" }));
  await userEvent.click(screen.getByRole("menuitemradio", { name: "Русский" }));
  expect(
    screen.getByRole("heading", { name: /Всё, что вы знаете/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Открыть проект Сырой проект" }),
  ).toBeInTheDocument();
  expect(document.documentElement.lang).toBe("ru");
  expect(localStorage.getItem("ygg-language")).toBe("ru");
  expect(savedLanguage()).toBe("ru");
  view.unmount();
  render(content);
  expect(screen.getByRole("button", { name: "Язык" })).toHaveAttribute(
    "title",
    "Русский",
  );
});
it("updates utility labels and formats numbers and dates for the active language", () => {
  act(() => setLanguage("de"));
  expect(typeName("decision")).toBe("Entscheidung");
  expect(translate("de", "{count} memories", { count: 1500 })).toBe(
    "1.500 Einträge",
  );
  expect(date(1700000000)).toBe(
    new Date(1700000000 * 1000).toLocaleDateString("de", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }),
  );
});
it("keeps translating when local storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  act(() => setLanguage("ja"));
  expect(getLanguage()).toBe("ja");
  expect(translate("ja", "Projects")).toBe("プロジェクト");
  vi.restoreAllMocks();
});
it("updates independently mounted consumers", async () => {
  function Consumer() {
    const { t } = useI18n();
    return <p>{t("Projects")}</p>;
  }
  render(
    <>
      <LanguagePicker />
      <Consumer />
    </>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Language" }));
  await userEvent.click(screen.getByRole("menuitemradio", { name: "中文" }));
  expect(screen.getByText("项目")).toBeInTheDocument();
});

it("preserves unknown raw errors, including object property names", () => {
  expect(translate("ru", "Provider error: {detail}")).toBe(
    "Provider error: {detail}",
  );
  expect(translate("de", "constructor")).toBe("constructor");
  expect(translate("ja", "toString")).toBe("toString");
});
