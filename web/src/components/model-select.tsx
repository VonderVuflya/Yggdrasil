import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { request } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Button } from "./ui/button";
interface Model {
  id: string;
  kind: string;
  size?: string;
  note?: string;
}
export function ModelSelect({
  id,
  provider,
  url,
  value,
  onChange,
  purpose,
  apiKey,
  onAvailable,
}: {
  id: string;
  provider: "ollama" | "openai";
  url: string;
  value: string;
  onChange: (value: string) => void;
  purpose: "chat" | "bg" | "embed";
  apiKey?: string;
  onAvailable?: (value: boolean) => void;
}) {
  const { t } = useI18n();
  const [models, setModels] = useState<Model[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const key = useRef(apiKey);
  key.current = apiKey;
  const available = useRef(onAvailable);
  available.current = onAvailable;
  useEffect(() => {
    const controller = new AbortController();
    setModels([]);
    setError("");
    setBusy(true);
    available.current?.(false);
    const timer = setTimeout(() => {
      request<{ models: Model[]; reachable: boolean; error?: string }>(
        "/api/models",
        {
          provider,
          url,
          purpose,
          ...(key.current !== undefined ? { api_key: key.current } : {}),
        },
        undefined,
        controller.signal,
      )
        .then((data) => {
          if (controller.signal.aborted) return;
          setModels(data.models);
          if (!data.reachable)
            setError(data.error || "Model server is unavailable.");
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [provider, url, purpose, version]);
  useEffect(() => {
    available.current?.(!busy && models.some((m) => m.id === value));
  }, [models, busy, value]);
  const present = models.some((m) => m.id === value);
  return (
    <div className="model-picker">
      <div className="flex items-center gap-2">
        <select
          id={id}
          className="min-w-0 flex-1 max-w-none"
          value={value}
          disabled={busy}
          onChange={(e) => onChange(e.target.value)}
          aria-label={t("Installed model")}
        >
          <option value="">
            {t(busy ? "Loading models…" : "Select an installed model")}
          </option>
          {value && !present && (
            <option value={value} disabled>
              {value} — {t("Not available")}
            </option>
          )}
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}
              {m.size ? ` (${m.size})` : ""}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          type="button"
          size="icon"
          aria-label={t("Refresh models")}
          disabled={busy}
          onClick={() => setVersion((v) => v + 1)}
        >
          <RefreshCw size={16} className={busy ? "animate-spin" : ""} />
        </Button>
      </div>
      {error ? (
        <p role="status" className="field-hint text-destructive">
          {t(error)}
        </p>
      ) : !busy && !models.length ? (
        <p role="status" className="field-hint">
          {t(
            "No installed models found. Download a model in your model server, then refresh.",
          )}
        </p>
      ) : (
        <p className="field-hint">
          {t(
            "Models available on the selected server. No download is started.",
          )}
        </p>
      )}
    </div>
  );
}
