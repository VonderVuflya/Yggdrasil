import { WORKSPACE_FEATURES } from "../lib/features";
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Server,
  ShieldCheck,
  Settings2,
  MessageSquare,
  Palette,
} from "lucide-react";
import { useSearchParams, Link } from "react-router-dom";
import type { Settings } from "../lib/types";
import { useResource } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { request } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ErrorNotice, Loading } from "../components/common";
import { ModelSelect } from "../components/model-select";
import { ConfigurationPanel } from "./configuration";
import { AppearancePanel } from "./appearance";
export function SettingsPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const section = params.get("section");
  const tab =
    section === "appearance"
      ? "appearance"
      : section === "chat" && WORKSPACE_FEATURES.chat
        ? "chat"
        : "config";
  return (
    <>
      <header className="page-heading">
        <h1>{t("Workspace settings")}</h1>
        <p>{t("Manage your models and the shared Yggdrasil configuration.")}</p>
      </header>
      <div className="settings-nav">
        {WORKSPACE_FEATURES.chat && (
          <Button
            variant={tab === "chat" ? "secondary" : "ghost"}
            onClick={() => setParams({ section: "chat" })}
          >
            <MessageSquare />
            {t("Chat model")}
          </Button>
        )}
        <Button
          variant={tab === "config" ? "secondary" : "ghost"}
          onClick={() => setParams({ section: "config" })}
        >
          <Settings2 />
          {t("Yggdrasil configuration")}
        </Button>
        <Button
          variant={tab === "appearance" ? "secondary" : "ghost"}
          onClick={() => setParams({ section: "appearance" })}
        >
          <Palette />
          {t("Appearance")}
        </Button>
        <Link
          className="text-sm text-primary underline ml-auto"
          to="/operations"
        >
          {t("Open operations")}
        </Link>
      </div>
      {tab === "config" ? (
        <ConfigurationPanel />
      ) : tab === "appearance" ? (
        <AppearancePanel />
      ) : (
        <ChatSettings />
      )}
    </>
  );
}
function ChatSettings() {
  const { t } = useI18n();
  const { value, loading, error, reload } =
    useResource<Settings>("/api/settings");
  const [provider, setProvider] = useState<"ollama" | "openai">("ollama");
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [keyChanged, setKeyChanged] = useState(false);
  const [available, setAvailable] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (value) {
      setProvider(value.provider || "ollama");
      setUrl(value.url || value.suggested_url || "");
      setModel(value.model || value.suggested_model || "");
      setKey("");
      setKeyChanged(false);
    }
  }, [value]);
  let remote = false;
  let host = "";
  try {
    host = new URL(url).hostname;
    remote = !["localhost", "127.0.0.1", "::1", "[::1]"].includes(host);
  } catch {
    /* field validation */
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!available) return;
    setSaving(true);
    setSaveError("");
    setSaved(false);
    try {
      await request(
        "/api/settings",
        { provider, url, model, ...(keyChanged ? { api_key: key } : {}) },
        "PUT",
      );
      setSaved(true);
      reload();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return loading ? (
    <Loading />
  ) : error ? (
    <ErrorNotice error={error} retry={reload} />
  ) : (
    <div className="settings-layout">
      <form onSubmit={save} className="settings-card">
        <div className="flex items-start gap-4">
          <div className="detail-icon">
            <Server size={22} />
          </div>
          <div>
            <h2>{t("Chat model")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("Chat settings do not change the import or embedding model.")}
            </p>
          </div>
        </div>
        <div className="mt-7 space-y-5">
          <div>
            <label htmlFor="provider">{t("Model server API")}</label>
            <select
              id="provider"
              className="mt-2 w-full max-w-none"
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value as "ollama" | "openai");
                setSaved(false);
              }}
            >
              <option value="ollama">Ollama</option>
              <option value="openai">
                {t("OpenAI-compatible API / LM Studio")}
              </option>
            </select>
          </div>
          <div>
            <label htmlFor="model-url">{t("Server address")}</label>
            <Input
              className="mt-2"
              id="model-url"
              type="url"
              required
              placeholder="http://127.0.0.1:11434"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setSaved(false);
              }}
            />
          </div>
          <div>
            <label htmlFor="api-key">{t("API key (optional)")}</label>
            <Input
              className="mt-2"
              id="api-key"
              type="password"
              autoComplete="new-password"
              placeholder={
                value?.has_key
                  ? t("Saved secret — leave unchanged to keep")
                  : t("Not usually needed for local models")
              }
              value={key}
              onChange={(e) => {
                setKey(e.target.value);
                setKeyChanged(true);
                setSaved(false);
              }}
            />
            {value?.has_key && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setKey("");
                  setKeyChanged(true);
                }}
              >
                {t("Clear saved key on save")}
              </Button>
            )}
          </div>
          {value?.has_key &&
            (url.replace(/\/$/, "") !== value.url ||
              provider !== value.provider) && (
              <p className="field-hint">
                {t(
                  "Changing the server clears the saved API key unless you enter a new one.",
                )}
              </p>
            )}
          <div>
            <label htmlFor="model-name">{t("Installed model")}</label>
            <div className="mt-2">
              <ModelSelect
                id="model-name"
                provider={provider}
                url={url}
                value={model}
                onChange={(v) => {
                  setModel(v);
                  setSaved(false);
                }}
                purpose="chat"
                apiKey={keyChanged ? key : undefined}
                onAvailable={setAvailable}
              />
            </div>
          </div>
          {remote && (
            <div className="notice">
              <ShieldCheck size={18} />
              <p>
                {t(
                  "Questions and retrieved memory fragments will be sent to {host}.",
                  { host },
                )}
              </p>
            </div>
          )}
          {saveError && <ErrorNotice error={saveError} />}
          <div className="flex flex-wrap items-center gap-4">
            <Button disabled={saving || !available} type="submit">
              {t(saving ? "Saving…" : "Save connection")}
            </Button>
            {saved && (
              <span
                role="status"
                className="flex items-center gap-2 text-sm text-primary"
              >
                <CheckCircle2 size={17} />
                {t("Connection saved.")}
              </span>
            )}
          </div>
        </div>
      </form>
      <aside className="space-y-5">
        <div className="info-panel">
          <h3>{t("Your installed models")}</h3>
          <p>
            {t(
              "The selector reads the models from your server. Start Ollama or LM Studio and refresh the list.",
            )}
          </p>
        </div>
        <div className="info-panel">
          <h3>{t("Knowledge remains available")}</h3>
          <p>
            {t(
              "Without a model, you can browse projects, explore the graph and search your memories.",
            )}
          </p>
        </div>
      </aside>
    </div>
  );
}
