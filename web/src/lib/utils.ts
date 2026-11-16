import { t, getLanguage } from "./i18n";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export const projectName = (name: string | null) =>
  name === null ? t("All projects") : name || t("No project");
export const typeName = (type: string) =>
  ({
    decision: t("Decision"),
    lesson: t("Lesson"),
    fix: t("Fix"),
    convention: t("Convention"),
    project_status: t("Status"),
    follow_up: t("Open question"),
    reference: t("Reference"),
    memory: t("Memory"),
    note: t("Note"),
  })[type] ||
  type ||
  t("Memory");
export const date = (value: number) =>
  value
    ? new Date(value * 1000).toLocaleDateString(getLanguage(), {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : t("No data");
export const excerpt = (value: string, n = 180) =>
  value.length > n ? `${value.slice(0, n)}…` : value;
export function projectUrl(name: string, tab = "overview", chat?: string) {
  const q = new URLSearchParams({ project: name, tab });
  if (chat) q.set("chat", chat);
  return `/project?${q}`;
}
