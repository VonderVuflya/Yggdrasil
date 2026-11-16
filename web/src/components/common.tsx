import { t, useI18n } from "../lib/i18n";
import { AlertCircle, ArrowUpRight, FolderOpen, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { Link } from "react-router-dom";
export function ErrorNotice({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  useI18n();
  return (
    <div role="alert" className="error-notice">
      <AlertCircle size={18} />
      <div className="min-w-0 flex-1">
        <p>{t(error)}</p>
        {error.includes("401") ||
        error.toLowerCase().includes("сесси") ||
        error.toLowerCase().includes("session") ? (
          <p className="mt-1 text-sm">
            {t("Reopen the app using")} <code>ygg</code>.
          </p>
        ) : null}
      </div>
      {retry && (
        <Button variant="ghost" size="sm" onClick={retry}>
          <RefreshCw />
          {t("Retry")}
        </Button>
      )}
    </div>
  );
}
export function Loading({
  label = t("Loading knowledge…"),
}: {
  label?: string;
}) {
  useI18n();
  return (
    <div role="status" className="space-y-3 py-8">
      <p className="text-sm text-muted-foreground">{label}</p>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-16 rounded-xl bg-muted motion-safe:animate-pulse"
        />
      ))}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  useI18n();
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <FolderOpen size={25} />
      </div>
      <h3>{title}</h3>
      <div className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        {children}
      </div>
    </div>
  );
}
export function SettingsLink() {
  useI18n();
  return (
    <Link
      className="inline-flex items-center gap-1 text-sm font-semibold text-primary underline-offset-4 hover:underline"
      to="/settings"
    >
      {t("Configure a model")}
      <ArrowUpRight size={14} />
    </Link>
  );
}
export function Badge({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  useI18n();
  return <span className={`badge ${className}`}>{children}</span>;
}
