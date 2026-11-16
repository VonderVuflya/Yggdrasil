import { t, useI18n, I18nProvider } from "./lib/i18n";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/manrope/cyrillic-400.css";
import "@fontsource/manrope/cyrillic-500.css";
import "@fontsource/manrope/cyrillic-600.css";
import "@fontsource/manrope/cyrillic-700.css";
import "./styles.css";
import { App } from "./App";
import { establishSession, request } from "./lib/api";
import { Button } from "./components/ui/button";
import { ErrorNotice } from "./components/common";
import { Sprout } from "lucide-react";
import { initializeTheme } from "./lib/theme";
initializeTheme();
const session = establishSession().then(() =>
  request<{ engine: boolean; user_id: string; namespace: string }>(
    "/api/status",
  ),
);
function Root() {
  useI18n();
  const [status, setStatus] = useState<{
    engine: boolean;
    user_id: string;
    namespace: string;
  }>();
  const [error, setError] = useState("");
  useEffect(() => {
    session.then(setStatus).catch((e) => setError(e.message));
  }, []);
  if (!status)
    return (
      <div className="boot-screen">
        <div className="brand-icon">
          <Sprout size={30} />
        </div>
        <h1>Yggdrasil</h1>
        {error ? (
          <>
            <ErrorNotice error={error} />
            <p>
              {t("To open your secure local workspace, run")} <code>ygg</code>{" "}
              {t("in your terminal.")}
            </p>
            <Button variant="outline" onClick={() => location.reload()}>
              {t("Reconnect")}
            </Button>
          </>
        ) : (
          <p role="status">{t("Opening your knowledge workspace…")}</p>
        )}
      </div>
    );
  return (
    <BrowserRouter>
      <App status={status} />
    </BrowserRouter>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <Root />
    </I18nProvider>
  </StrictMode>,
);
