// shadcn/ui Sonner adapter, using the Workspace theme instead of next-themes.
import type { CSSProperties } from "react";
import {
  CircleCheck,
  Info,
  Loader2,
  OctagonX,
  TriangleAlert,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useTheme } from "../../lib/theme";
import { useI18n } from "../../lib/i18n";
export function Toaster(props: ToasterProps) {
  const { theme } = useTheme();
  const { t } = useI18n();
  return (
    <Sonner
      theme={theme.mode}
      className="toaster group"
      position="bottom-right"
      closeButton
      containerAriaLabel={t("Notifications")}
      icons={{
        success: <CircleCheck className="size-4 text-[var(--success)]" />,
        info: <Info className="size-4" />,
        warning: <TriangleAlert className="size-4" />,
        error: <OctagonX className="size-4 text-destructive" />,
        loading: <Loader2 className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--card)",
          "--normal-text": "var(--foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "12px",
        } as CSSProperties
      }
      {...props}
    />
  );
}
