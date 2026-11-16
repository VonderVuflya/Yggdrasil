import { useSyncExternalStore } from "react";

export const palettes = ["neutral", "green", "blue", "orange", "pink"] as const;
export type Palette = (typeof palettes)[number];
export type Mode = "light" | "dark";
export interface Theme {
  palette: Palette;
  mode: Mode;
}
export const paletteLabels: Record<Palette, string> = {
  neutral: "Neutral",
  green: "Green",
  blue: "Blue",
  orange: "Orange",
  pink: "Pink",
};

// Surface, text, card, accent, accent text, secondary, muted text, border, input.
// Each pair is tuned independently: light tints / deep ink, never an inverted palette.
const colors: Record<Palette, Record<Mode, readonly string[]>> = {
  neutral: {
    light: [
      "#f5f5f6",
      "#202124",
      "#ffffff",
      "#34363b",
      "#ffffff",
      "#e9eaec",
      "#62646c",
      "#d3d4d8",
      "#868890",
    ],
    dark: [
      "#141517",
      "#f1f1f3",
      "#1e2023",
      "#d5d7dd",
      "#202124",
      "#2e3036",
      "#b1b3bd",
      "#45474f",
      "#777a85",
    ],
  },
  green: {
    light: [
      "#f3f6f4",
      "#182c27",
      "#ffffff",
      "#24634c",
      "#ffffff",
      "#e3ede6",
      "#53665e",
      "#cbdacf",
      "#738d7d",
    ],
    dark: [
      "#14221e",
      "#eef5f0",
      "#1e3029",
      "#98d4b2",
      "#142b1e",
      "#30483b",
      "#b0c3b8",
      "#496257",
      "#789785",
    ],
  },
  blue: {
    light: [
      "#f2f5fa",
      "#1c2c43",
      "#ffffff",
      "#285d9e",
      "#ffffff",
      "#e2eaf5",
      "#52657d",
      "#cad6e7",
      "#788da8",
    ],
    dark: [
      "#141e2e",
      "#edf3fc",
      "#1c2b40",
      "#9dc5fa",
      "#142b49",
      "#2a405c",
      "#b0c3dd",
      "#465e7d",
      "#7894b7",
    ],
  },
  orange: {
    light: [
      "#faf5ef",
      "#38291f",
      "#fffdfa",
      "#97501c",
      "#ffffff",
      "#f1e5d6",
      "#78614e",
      "#e0cdb9",
      "#a28a70",
    ],
    dark: [
      "#261d16",
      "#faf1e6",
      "#34271d",
      "#eeb77e",
      "#38220f",
      "#4b3828",
      "#d0bba6",
      "#70543e",
      "#a7896c",
    ],
  },
  pink: {
    light: [
      "#faf3f6",
      "#3b2531",
      "#fffdfd",
      "#9c3e68",
      "#ffffff",
      "#f1e1e9",
      "#7b596b",
      "#e2cbd6",
      "#a88295",
    ],
    dark: [
      "#281923",
      "#faedf4",
      "#392532",
      "#eba6c5",
      "#3b1c2d",
      "#503448",
      "#d2b6c7",
      "#755166",
      "#aa819a",
    ],
  },
};

export function themeTokens({ palette, mode }: Theme): Record<string, string> {
  const [
    background,
    foreground,
    card,
    primary,
    primaryForeground,
    secondary,
    mutedForeground,
    border,
    input,
  ] = colors[palette][mode];
  const dark = mode === "dark";
  return {
    "--background": background,
    "--foreground": foreground,
    "--card": card,
    "--card-foreground": foreground,
    "--primary": primary,
    "--primary-foreground": primaryForeground,
    "--secondary": secondary,
    "--secondary-foreground": foreground,
    "--muted": secondary,
    "--muted-foreground": mutedForeground,
    "--border": border,
    "--input": input,
    "--ring": primary,
    "--sidebar": dark ? background : secondary,
    "--sidebar-foreground": foreground,
    "--sidebar-muted": mutedForeground,
    "--sidebar-hover": dark ? secondary : card,
    "--sidebar-active": primary,
    "--sidebar-active-foreground": primaryForeground,
    "--destructive": dark ? "#ffaaaa" : "#ad3038",
    "--destructive-foreground": dark ? "#341719" : "#ffffff",
    "--success": dark ? "#a9d4ac" : "#2a673b",
    "--warning": dark ? "#e7bd82" : "#8b591d",
    "--graph-node": primary,
    "--graph-selected": foreground,
    "--graph-edge": mutedForeground,
  };
}

const validPalette = (value: unknown): value is Palette =>
  palettes.includes(value as Palette);
export function savedTheme(): Theme {
  try {
    const palette = localStorage.getItem("ygg-palette");
    return {
      palette: validPalette(palette) ? palette : "green",
      mode: localStorage.getItem("ygg-theme") === "dark" ? "dark" : "light",
    };
  } catch {
    return { palette: "green", mode: "light" };
  }
}
let current: Theme = savedTheme();
const listeners = new Set<() => void>();
const subscribe = (callback: () => void) => {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
};
export const getTheme = () => current;
function apply(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme.mode === "dark");
  root.dataset.palette = theme.palette;
  root.dataset.mode = theme.mode;
  root.style.colorScheme = theme.mode;
  for (const [key, value] of Object.entries(themeTokens(theme)))
    root.style.setProperty(key, value);
  window.dispatchEvent(new Event("ygg-theme-changed"));
}
function update(theme: Theme) {
  const changed =
    current.palette !== theme.palette || current.mode !== theme.mode;
  current = changed ? theme : current;
  apply(current);
  if (changed) listeners.forEach((callback) => callback());
}
export function setTheme(next: Partial<Theme>) {
  const theme = {
    palette: validPalette(next.palette) ? next.palette : current.palette,
    mode:
      next.mode === "light" || next.mode === "dark" ? next.mode : current.mode,
  };
  try {
    localStorage.setItem("ygg-palette", theme.palette);
    localStorage.setItem("ygg-theme", theme.mode);
  } catch {
    /* Appearance remains usable when browser storage is blocked. */
  }
  update(theme);
}
let initialized = false;
export function initializeTheme() {
  update(savedTheme());
  if (initialized) return;
  initialized = true;
  window.addEventListener("storage", (event) => {
    if (
      event.key === null ||
      event.key === "ygg-theme" ||
      event.key === "ygg-palette"
    )
      update(savedTheme());
  });
}
export function useTheme() {
  return {
    theme: useSyncExternalStore(subscribe, getTheme, getTheme),
    setTheme,
  };
}
