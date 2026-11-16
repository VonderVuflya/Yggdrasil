import type { CSSProperties } from "react";
import { Check, Moon, Sun } from "lucide-react";
import { useI18n } from "../lib/i18n";
import {
  palettes,
  paletteLabels,
  themeTokens,
  useTheme,
  type Mode,
} from "../lib/theme";

export function AppearancePanel() {
  const { t } = useI18n();
  const { theme, setTheme } = useTheme();
  return (
    <section className="settings-card appearance-panel">
      <h2>{t("Appearance")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {t(
          "Make this workspace feel like yours. Changes apply immediately and are saved in this browser.",
        )}
      </p>
      <fieldset className="appearance-section">
        <legend>{t("Theme mode")}</legend>
        <div className="appearance-modes">
          {(["light", "dark"] as Mode[]).map((mode) => (
            <label className="appearance-mode" key={mode}>
              <input
                className="sr-only"
                type="radio"
                name="theme-mode"
                value={mode}
                checked={theme.mode === mode}
                onChange={() => setTheme({ mode })}
              />
              <span>
                {mode === "light" ? (
                  <Sun size={18} aria-hidden="true" />
                ) : (
                  <Moon size={18} aria-hidden="true" />
                )}
                {t(mode === "light" ? "Light" : "Dark")}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="appearance-section">
        <legend>{t("Color palette")}</legend>
        <p className="field-hint mb-4">
          {t("Every palette has a light and a dark version.")}
        </p>
        <div className="palette-grid">
          {palettes.map((palette) => (
            <label className="palette-option" key={palette}>
              <input
                className="sr-only"
                type="radio"
                name="theme-palette"
                value={palette}
                checked={theme.palette === palette}
                onChange={() => setTheme({ palette })}
              />
              <span className="palette-card">
                <span
                  className="palette-preview"
                  aria-hidden="true"
                  style={
                    themeTokens({ palette, mode: theme.mode }) as CSSProperties
                  }
                >
                  <span className="palette-preview-sidebar">
                    <i />
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="palette-preview-content">
                    <i className="palette-preview-heading" />
                    <span className="palette-preview-message">
                      <i />
                      <i />
                    </span>
                    <i className="palette-preview-action" />
                  </span>
                </span>
                <span className="palette-caption">
                  <span>{t(paletteLabels[palette])}</span>
                  <Check
                    size={17}
                    aria-hidden="true"
                    className="palette-check"
                  />
                </span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
    </section>
  );
}
