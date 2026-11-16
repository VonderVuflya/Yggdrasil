import {
  ArrowUpCircle,
  CheckCircle2,
  Github,
  Loader2,
  Star,
} from "lucide-react";
import { useI18n, formatNumber } from "../lib/i18n";
import type { ReleaseController } from "../lib/releases";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "./ui/dialog";
const repository = "https://github.com/VonderVuflya/Yggdrasil";
export function VersionBadge({ release }: { release: ReleaseController }) {
  const { t } = useI18n();
  const { info, busy, setOpen } = release;
  const text = info ? `v${info.current}` : t("Version");
  if (!busy && !info?.available && !(info?.restart_required && info?.update))
    return (
      <a
        className="version-badge"
        href={`${repository}/releases`}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${text} · ${t("Release notes")}`}
      >
        {text}
      </a>
    );
  return (
    <button
      className="version-badge"
      onClick={() => setOpen(true)}
      aria-label={`${text} · ${t(busy ? "Updating Yggdrasil…" : info?.restart_required ? "Restart Workspace" : "Update available")}`}
    >
      {text}
      {busy ? (
        <Loader2 size={13} className="animate-spin" aria-hidden="true" />
      ) : (
        <ArrowUpCircle size={13} aria-hidden="true" />
      )}
    </button>
  );
}
export function GitHubButton({ release }: { release: ReleaseController }) {
  const { t } = useI18n();
  const stars = release.info?.stars;
  return (
    <a
      className="github-button"
      href={repository}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={
        typeof stars === "number"
          ? t("GitHub project · {count} stars", { count: stars })
          : t("GitHub project")
      }
      title={t("GitHub project")}
    >
      <Github size={18} aria-hidden="true" />
      <span className="github-stars">
        <Star size={14} aria-hidden="true" />
        <span>{typeof stars === "number" ? formatNumber(stars) : "—"}</span>
      </span>
    </a>
  );
}
export function UpdateDialog({ release }: { release: ReleaseController }) {
  const { t } = useI18n();
  const {
    info,
    open,
    setOpen,
    busy,
    starting,
    restarting,
    error,
    start,
    retryRestart,
  } = release;
  const update = info?.update;
  const failed = update?.status === "failed" || update?.status === "stopped";
  const complete = update?.status === "completed" && !info?.restart_required;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="update-dialog">
        <DialogTitle>{t("Update Yggdrasil")}</DialogTitle>
        <DialogDescription className="mt-3">
          {t(
            "Install the latest version? Yggdrasil will update and restart Workspace. Your saved data stays in place.",
          )}
        </DialogDescription>
        <div className="update-versions">
          <span>v{info?.current || "…"}</span>
          <span aria-hidden="true">→</span>
          <strong>v{info?.latest || update?.target || "…"}</strong>
        </div>
        {(busy || update) && (
          <div className="update-state" role="status">
            {busy ? (
              <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            ) : complete ? (
              <CheckCircle2 className="size-5" aria-hidden="true" />
            ) : null}
            <span>
              {t(
                restarting
                  ? "Restarting Workspace…"
                  : starting
                    ? "Starting update…"
                    : busy
                      ? "Updating Yggdrasil…"
                      : complete
                        ? "Update complete"
                        : "Update failed",
              )}
            </span>
          </div>
        )}
        {update && (
          <pre
            className="update-output"
            tabIndex={0}
            aria-label={t("Update output")}
          >
            {update.output || t("Waiting for output…")}
          </pre>
        )}
        {(error || update?.error) && (
          <p className="mt-4 text-sm text-destructive" role="alert">
            {t(error || update?.error || "")}
          </p>
        )}
        {busy && (
          <p className="field-hint mt-3">
            {t(
              "You can hide this window. The update will continue in the background.",
            )}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t(busy ? "Hide" : "Close")}
          </Button>
          {!busy &&
            info?.restart_required &&
            update?.status === "completed" && (
              <Button onClick={retryRestart}>{t("Restart Workspace")}</Button>
            )}
          {!busy && (info?.available || failed) && (
            <Button onClick={() => void start()}>
              {t(failed ? "Retry update" : "Update now")}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
