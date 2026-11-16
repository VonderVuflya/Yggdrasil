import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { request } from "./api";
import { t } from "./i18n";
export interface UpdateOperation {
  id: string;
  target: string;
  previous: string;
  status: "running" | "completed" | "failed" | "stopped";
  output: string;
  exit_code: number | null;
  error?: string | null;
}
export interface ReleaseInfo {
  current: string;
  running: string;
  latest: string | null;
  available: boolean;
  stars: number | null;
  repository: string;
  releases: string;
  checking: boolean;
  check_error: boolean;
  restart_required: boolean;
  update: UpdateOperation | null;
}
export function useRelease() {
  const [info, setInfo] = useState<ReleaseInfo>();
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const restartStarted = useRef(false);
  const restartDeadline = useRef(0);
  const restartFailed = useRef(false);
  const notified = useRef(new Set<string>());
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      let delay = 30000;
      try {
        const value = await request<ReleaseInfo>(
          "/api/release",
          undefined,
          undefined,
          controller.signal,
        );
        if (disposed) return;
        setInfo(value);
        const update = value.update;
        if (
          value.checking ||
          update?.status === "running" ||
          restartStarted.current
        )
          delay = 1500;
        if (update?.status === "completed") {
          if (value.restart_required) {
            delay = 1500;
            if (!restartStarted.current) {
              restartStarted.current = true;
              restartDeadline.current = Date.now() + 60000;
              setRestarting(true);
              try {
                await request(
                  "/api/release/restart",
                  {},
                  undefined,
                  controller.signal,
                );
              } catch (e) {
                if (disposed) return;
                restartFailed.current = true;
                setRestarting(false);
                setError((e as Error).message);
              }
            } else if (
              !restartFailed.current &&
              Date.now() > restartDeadline.current
            ) {
              restartFailed.current = true;
              setError(
                t(
                  "Workspace could not restart. Open the update details and try again.",
                ),
              );
              setRestarting(false);
            }
          } else if (restartStarted.current) {
            window.location.reload();
            return;
          } else {
            let shown = notified.current.has(update.id);
            try {
              shown ||=
                sessionStorage.getItem("ygg-update-notified") === update.id;
            } catch {
              /* optional storage */
            }
            if (!shown) {
              toast.success(
                t("Yggdrasil updated to {version}", { version: value.current }),
              );
              notified.current.add(update.id);
              try {
                sessionStorage.setItem("ygg-update-notified", update.id);
              } catch {
                /* optional storage */
              }
              window.dispatchEvent(new Event("ygg-data-changed"));
            }
          }
        }
        if (!restartStarted.current) setError("");
      } catch (e) {
        if (disposed) return;
        if (
          restartStarted.current &&
          !restartFailed.current &&
          Date.now() <= restartDeadline.current
        )
          delay = 1500;
        else {
          setError((e as Error).message);
          setRestarting(false);
          delay = 5000;
        }
      } finally {
        if (!disposed) timer = setTimeout(poll, delay);
      }
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [retry]);
  async function start() {
    if (starting || restarting || info?.update?.status === "running") return;
    setStarting(true);
    setError("");
    try {
      const value = await request<ReleaseInfo>("/api/release/update", {
        confirmed: true,
      });
      setInfo(value);
      setRetry((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  function retryRestart() {
    restartStarted.current = false;
    restartFailed.current = false;
    setError("");
    setRetry((v) => v + 1);
  }
  return {
    info,
    open,
    setOpen,
    starting,
    restarting,
    error,
    start,
    retryRestart,
    busy: starting || restarting || info?.update?.status === "running",
  };
}
export type ReleaseController = ReturnType<typeof useRelease>;
