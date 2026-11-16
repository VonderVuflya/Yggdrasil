import { useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { request } from "../lib/api";
import { useResource } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ErrorNotice, Loading } from "../components/common";
import { ModelSelect } from "../components/model-select";
export interface ConfigSetting {
  key: string;
  value: string;
  stored_value: string | null;
  source: string;
  default: string;
  description: string;
  secret: boolean;
  has_value: boolean;
  restart_required: boolean;
  type: "string" | "number" | "select";
  options?: string[];
}
interface Configuration {
  groups: { id: string; label: string; settings: ConfigSetting[] }[];
  identity: { user_id: string; namespace: string };
}
export function ConfigurationPanel() {
  const { t } = useI18n();
  const config = useResource<Configuration>("/api/config");
  const [values, setValues] = useState<Record<string, string>>({});
  const [unset, setUnset] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [bgProvider, setBgProvider] = useState<"ollama" | "openai">("ollama");
  const all = config.value?.groups.flatMap((g) => g.settings) || [];
  const effective = (key: string) => {
    const setting = all.find((item) => item.key === key);
    if (setting?.source.startsWith("env:")) return setting.value;
    if (unset.includes(key)) return setting?.default ?? "";
    return values[key] ?? setting?.value ?? "";
  };
  const discoveryKey = (key: string) => {
    if (all.find((item) => item.key === key)?.source.startsWith("env:"))
      return undefined;
    return unset.includes(key) ? "" : values[key];
  };
  const backgroundUrl = effective("distill_url");
  useEffect(() => {
    if (backgroundUrl)
      setBgProvider(backgroundUrl.includes(":11434") ? "ollama" : "openai");
  }, [backgroundUrl]);
  function change(key: string, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setUnset((v) => v.filter((k) => k !== key));
    setSaved(false);
  }
  function reset(key: string) {
    setUnset((v) =>
      v.includes(key) ? v.filter((k) => k !== key) : [...v, key],
    );
    setValues((v) => {
      const next = { ...v };
      delete next[key];
      return next;
    });
    setSaved(false);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await request("/api/config", { values, unset }, "PUT");
      setValues({});
      setUnset([]);
      setSaved(true);
      config.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  if (config.loading) return <Loading />;
  if (config.error)
    return <ErrorNotice error={config.error} retry={config.reload} />;
  return (
    <form onSubmit={save} className="config-panel">
      <div className="section-heading">
        <div>
          <h2 className="flex items-center gap-2">
            <Settings2 size={22} />
            {t("Yggdrasil configuration")}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {t(
              "The same settings as ygg config. Changes are shared with the CLI.",
            )}
          </p>
        </div>
      </div>
      <div className="notice mb-6">
        <p>
          {t(
            "Environment variables take priority over saved settings. Restart the engine after changing embeddings. Identity changes apply to a new Workspace process.",
          )}
        </p>
      </div>
      {config.value?.groups.map((group) => (
        <section className="settings-card config-group" key={group.id}>
          <h3>{t(group.label)}</h3>
          <div className="config-fields">
            {group.settings.map((setting) => {
              const current =
                values[setting.key] ?? setting.stored_value ?? setting.value;
              const model =
                setting.key === "bg_model" || setting.key === "embed_model";
              const embed = setting.key === "embed_model";
              const provider = embed
                ? effective("embed_backend") === "openai"
                  ? "openai"
                  : "ollama"
                : bgProvider;
              return (
                <div className="config-field" key={setting.key}>
                  <div className="config-field-heading">
                    <label htmlFor={`config-${setting.key}`}>
                      <code>{setting.key}</code>
                    </label>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => reset(setting.key)}
                    >
                      {t(
                        unset.includes(setting.key)
                          ? "Keep saved value"
                          : "Reset to default",
                      )}
                    </Button>
                  </div>
                  {unset.includes(setting.key) ? (
                    <p className="field-hint">
                      {t("Saved value will be removed.")}
                    </p>
                  ) : model ? (
                    <>
                      {!embed && (
                        <select
                          aria-label={t("Model server API")}
                          className="w-full max-w-none mb-2"
                          value={bgProvider}
                          onChange={(e) =>
                            setBgProvider(e.target.value as "ollama" | "openai")
                          }
                        >
                          <option value="ollama">Ollama</option>
                          <option value="openai">
                            {t("OpenAI-compatible API / LM Studio")}
                          </option>
                        </select>
                      )}
                      <ModelSelect
                        id={`config-${setting.key}`}
                        provider={provider}
                        purpose={embed ? "embed" : "bg"}
                        url={effective(embed ? "embed_url" : "distill_url")}
                        value={current}
                        onChange={(v) => change(setting.key, v)}
                        apiKey={discoveryKey(
                          embed ? "embed_api_key" : "distill_api_key",
                        )}
                      />
                    </>
                  ) : setting.type === "select" ? (
                    <select
                      id={`config-${setting.key}`}
                      className="w-full max-w-none"
                      value={current}
                      onChange={(e) => change(setting.key, e.target.value)}
                    >
                      {setting.options?.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      id={`config-${setting.key}`}
                      value={current}
                      type={
                        setting.secret
                          ? "password"
                          : setting.type === "number"
                            ? "number"
                            : "text"
                      }
                      autoComplete={setting.secret ? "new-password" : undefined}
                      placeholder={
                        setting.secret && setting.has_value
                          ? t("Saved secret — leave unchanged to keep")
                          : setting.default
                      }
                      onChange={(e) => change(setting.key, e.target.value)}
                    />
                  )}
                  <p className="field-hint">{t(setting.description)}</p>
                  <div className="config-origin">
                    <span>
                      {t("Source")}: {setting.source}
                    </span>
                    {setting.source.startsWith("env:") && !setting.secret && (
                      <span>
                        {t("Effective value")}: {setting.value}
                      </span>
                    )}
                    {setting.restart_required && (
                      <span>{t("Engine restart required")}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      {error && <ErrorNotice error={error} />}
      <div className="config-save">
        <Button
          type="submit"
          disabled={saving || (!Object.keys(values).length && !unset.length)}
        >
          {t(saving ? "Saving…" : "Save configuration")}
        </Button>
        {saved && <span role="status">{t("Configuration saved.")}</span>}
      </div>
    </form>
  );
}
