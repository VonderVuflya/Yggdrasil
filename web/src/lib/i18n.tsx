import { Languages } from "lucide-react";
import { Button } from "../components/ui/button";
import { LanguageFlag } from "../components/language-flag";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "../components/ui/dropdown-menu";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import en from "./locales/en.json";
import ru from "./locales/ru.json";
import de from "./locales/de.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import ja from "./locales/ja.json";
import zh from "./locales/zh.json";

export const languages = {
  en: "English",
  ru: "Русский",
  de: "Deutsch",
  es: "Español",
  fr: "Français",
  ja: "日本語",
  zh: "中文",
} as const;
export type Language = keyof typeof languages;
export const catalogs: Record<Language, Record<string, string>> = {
  en,
  ru,
  de,
  es,
  fr,
  ja,
  zh,
};
const storageKey = "ygg-language";
const valid = (value: string | null): value is Language =>
  !!value && Object.hasOwn(languages, value);
export function savedLanguage(): Language {
  try {
    const value = localStorage.getItem(storageKey);
    return valid(value) ? value : "en";
  } catch {
    return "en";
  }
}
let language: Language = savedLanguage();
const listeners = new Set<() => void>();
export const getLanguage = () => language;
export function setLanguage(value: Language) {
  if (!valid(value)) return;
  language = value;
  try {
    localStorage.setItem(storageKey, value);
  } catch {
    /* Storage may be disabled. */
  }
  if (typeof document !== "undefined") document.documentElement.lang = value;
  listeners.forEach((listener) => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export const formatNumber = (value: number) =>
  new Intl.NumberFormat(language).format(value);
export function translate(
  locale: Language,
  key: string,
  vars?: Record<string, string | number>,
) {
  const value = Object.hasOwn(catalogs[locale], key)
    ? catalogs[locale][key]
    : Object.hasOwn(catalogs.en, key)
      ? catalogs.en[key]
      : key;
  return value.replace(/\{(\w+)\}/g, (token, name: string) => {
    const replacement = vars?.[name];
    return replacement === undefined
      ? token
      : typeof replacement === "number"
        ? new Intl.NumberFormat(locale).format(replacement)
        : replacement;
  });
}
export const t = (key: string, vars?: Record<string, string | number>) =>
  translate(language, key, vars);
export function useI18n() {
  const current = useSyncExternalStore(
    subscribe,
    getLanguage,
    () => "en" as Language,
  );
  return { t, language: current, setLanguage };
}
export function I18nProvider({ children }: { children: ReactNode }) {
  const { language: current } = useI18n();
  useEffect(() => {
    document.documentElement.lang = current;
    document.title = `Yggdrasil — ${t("Knowledge workspace")}`;
  }, [current]);
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey)
        setLanguage(valid(event.newValue) ? event.newValue : "en");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return children;
}
export function LanguagePicker() {
  const { language: current } = useI18n();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="language-trigger"
          aria-label={t("Language")}
          title={languages[current]}
        >
          <Languages size={19} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" aria-label={t("Language")}>
        <DropdownMenuRadioGroup
          value={current}
          onValueChange={(value) => setLanguage(value as Language)}
        >
          {Object.entries(languages).map(([code, label]) => (
            <DropdownMenuRadioItem key={code} value={code} lang={code}>
              <LanguageFlag language={code as Language} />
              <span>{label}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
