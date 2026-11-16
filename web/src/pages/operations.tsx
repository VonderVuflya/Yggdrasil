import { useEffect, useRef, useState } from "react";
import {
  Play,
  Square,
  Sprout,
  Stethoscope,
  RefreshCw,
  ArrowUp,
  ArrowDown,
  CornerDownLeft,
} from "lucide-react";
import { request } from "../lib/api";
import { useResource } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { parseArguments, quoteArguments } from "../lib/arguments";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ErrorNotice, Loading } from "../components/common";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import { CommandSelect } from "../components/command-select";
import { groupedCommands, type Command } from "../lib/commands";
import { Link } from "react-router-dom";
interface Job {
  id: string;
  command: string;
  args: string[];
  status: "running" | "completed" | "failed" | "stopped";
  output: string;
  exit_code: number | null;
  created_at: number;
  finished_at: number | null;
  interactive: boolean;
  truncated: boolean;
}
export function OperationsPage() {
  const { t } = useI18n();
  const catalog = useResource<{ commands: Command[] }>("/api/commands");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [command, setCommand] = useState("seed");
  const [args, setArgs] = useState("--dry-run");
  const [advanced, setAdvanced] = useState(false);
  const [selected, setSelected] = useState<string>();
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [input, setInput] = useState("");
  const [secret, setSecret] = useState(false);
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const response = await request<{ jobs: Job[] }>("/api/jobs");
        if (!disposed) setJobs(response.jobs);
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        if (!disposed) timer = setTimeout(load, 1500);
      }
    };
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [retry]);
  const seenJobs = useRef(new Set<string>());
  useEffect(() => {
    for (const item of jobs) {
      const key = `${item.id}:${item.status}`;
      if (item.status !== "running" && !seenJobs.current.has(key)) {
        seenJobs.current.add(key);
        window.dispatchEvent(new Event("ygg-data-changed"));
      }
    }
  }, [jobs]);
  const current = catalog.value?.commands.find((c) => c.name === command);
  const job = jobs.find((j) => j.id === selected) || jobs[0];
  const running = jobs.some((j) => j.status === "running");
  function choose(name: string) {
    setCommand(name);
    const chosen = catalog.value?.commands.find((c) => c.name === name);
    setArgs(quoteArguments(chosen?.example || []));
    setError("");
  }
  function toggleAdvanced(checked: boolean) {
    setAdvanced(checked);
    if (
      !checked &&
      !groupedCommands(catalog.value?.commands || [], false).some((group) =>
        group.commands.some((item) => item.name === command),
      )
    )
      choose("seed");
  }
  async function start(confirmed = false) {
    if (starting) return;
    setError("");
    let argv: string[];
    try {
      argv = parseArguments(args);
    } catch (e) {
      setError(t((e as Error).message));
      return;
    }
    if (current?.confirmation && !confirmed) {
      setConfirm(true);
      return;
    }
    setStarting(true);
    setConfirm(false);
    try {
      const created = await request<Job>("/api/jobs", {
        command,
        args: argv,
        confirmed,
      });
      setJobs((v) => [created, ...v.filter((j) => j.id !== created.id)]);
      setSelected(created.id);
      setRetry((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  async function action(suffix: string, body: unknown) {
    if (!job || pending) return;
    setPending(true);
    try {
      const updated = await request<Job>(`/api/jobs/${job.id}/${suffix}`, body);
      setJobs((v) => v.map((j) => (j.id === updated.id ? updated : j)));
      if (suffix === "input") setInput("");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <header className="page-heading">
        <h1>{t("Operations")}</h1>
        <p>
          {t("Import knowledge, check your system and maintain your memory.")}
        </p>
      </header>
      <div className="operation-shortcuts">
        {(
          [
            [
              "seed",
              "Import knowledge",
              "Turn saved conversations into project memory.",
              Sprout,
            ],
            [
              "doctor",
              "Check system health",
              "Find connection and configuration problems.",
              Stethoscope,
            ],
            [
              "sync",
              "Sync memory",
              "Keep memory in sync with your configured repository.",
              RefreshCw,
            ],
          ] as const
        ).map(([name, title, description, Icon]) => (
          <button
            key={name}
            className={`operation-shortcut ${command === name ? "active" : ""}`}
            aria-pressed={command === name}
            onClick={() => choose(name)}
          >
            <Icon size={20} aria-hidden="true" />
            <span>
              <strong>{t(title)}</strong>
              <span>{t(description)}</span>
            </span>
          </button>
        ))}
      </div>
      <p className="operation-guidance">
        {t("Choose a task, review the arguments, then run it.")}
      </p>
      <div className="operations-layout">
        <section className="settings-card">
          <h2>{t("Run a command")}</h2>
          {catalog.loading ? (
            <Loading />
          ) : catalog.error ? (
            <ErrorNotice error={catalog.error} retry={catalog.reload} />
          ) : (
            <form
              className="mt-5 space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                void start();
              }}
            >
              <div>
                <label htmlFor="operation-command">{t("Command")}</label>
                <CommandSelect
                  commands={catalog.value?.commands || []}
                  value={command}
                  onChange={choose}
                  advanced={advanced}
                />
                <p className="field-hint">
                  {current && t(current.description)}
                </p>
              </div>
              <div className="operation-advanced">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={advanced}
                    onChange={(event) => toggleAdvanced(event.target.checked)}
                  />
                  {t("Show advanced commands")}
                </label>
                <p className="field-hint">
                  {t(
                    "Memory editing, setup and agent integrations. All commands remain available in the CLI.",
                  )}
                </p>
              </div>
              <div>
                <label htmlFor="operation-args">{t("Arguments")}</label>
                <Input
                  id="operation-args"
                  className="mt-2 font-mono"
                  value={args}
                  onChange={(e) => setArgs(e.target.value)}
                  placeholder={command === "seed" ? "--dry-run" : "--help"}
                />
                <p className="field-hint">
                  {t(
                    "Use quotes for paths with spaces. Arguments are passed directly; no shell commands are evaluated.",
                  )}
                </p>
              </div>
              {command === "seed" && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setArgs("--dry-run")}
                  >
                    {t("Preview import")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setArgs("--yes")}
                  >
                    {t("Import new knowledge")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setArgs("--schedule 03:30")}
                  >
                    {t("Schedule nightly import")}
                  </Button>
                </div>
              )}
              <Button disabled={starting || running} type="submit">
                <Play />
                {t(starting ? "Starting…" : "Start command")}
              </Button>
              {running && (
                <p className="field-hint">
                  {t(
                    "Wait for the running command or stop it before starting another.",
                  )}
                </p>
              )}
            </form>
          )}
        </section>
        <section className="settings-card job-history">
          <div className="flex items-center justify-between">
            <h2>{t("Recent operations")}</h2>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("Refresh operations")}
              onClick={() => setRetry((v) => v + 1)}
            >
              <RefreshCw />
            </Button>
          </div>
          {jobs.length ? (
            <div className="mt-4 space-y-2">
              {jobs.map((j) => (
                <button
                  className={`job-item ${job?.id === j.id ? "active" : ""}`}
                  key={j.id}
                  onClick={() => setSelected(j.id)}
                >
                  <span>ygg {j.command}</span>
                  <span className="text-xs">{t(j.status)}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              {t("No commands have been run in this Workspace session.")}
            </p>
          )}
          <p className="field-hint mt-4">
            {t(
              "History is kept while Workspace is running. Command output is not translated.",
            )}
          </p>
        </section>
      </div>
      <p className="operation-footer-note">
        {t("Configuration has its own page.")}{" "}
        <Link to="/settings?section=config">{t("Open settings")}</Link>{" "}
        {t("Use the version badge for updates.")}
      </p>
      {error && (
        <div className="mt-4">
          <ErrorNotice error={error} />
        </div>
      )}
      {job && (
        <section className="job-console">
          <div className="job-console-heading">
            <div>
              <h2>ygg {job.command}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t(job.status)}
                {job.exit_code !== null
                  ? ` · ${t("Exit code")}: ${job.exit_code}`
                  : ""}
              </p>
            </div>
            {job.status === "running" && (
              <Button
                variant="outline"
                disabled={pending}
                onClick={() => action("stop", {})}
              >
                <Square />
                {t("Stop command")}
              </Button>
            )}
          </div>
          <pre tabIndex={0} aria-label={t("Command output")}>
            {job.output || t("Waiting for output…")}
          </pre>
          {job.truncated && (
            <p className="field-hint">
              {t("Older output was trimmed to keep the log bounded.")}
            </p>
          )}
          {job.status === "running" && job.interactive && (
            <form
              className="job-input"
              onSubmit={(e) => {
                e.preventDefault();
                void action("input", { text: input + "\n", secret });
              }}
            >
              <label htmlFor="job-answer">{t("Reply to a prompt")}</label>
              <div className="flex gap-2">
                <Input
                  id="job-answer"
                  type={secret ? "password" : "text"}
                  autoComplete="off"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={pending}
                />
                <Button type="submit" disabled={pending}>
                  {t("Send input")}
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 mr-3">
                  <input
                    type="checkbox"
                    checked={secret}
                    onChange={(e) => setSecret(e.target.checked)}
                  />
                  {t("Hide input")}
                </label>
                <details className="terminal-controls">
                  <summary>{t("Terminal controls")}</summary>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pending}
                      onClick={() => action("input", { text: "\u001b[A" })}
                    >
                      <ArrowUp />
                      {t("Up")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pending}
                      onClick={() => action("input", { text: "\u001b[B" })}
                    >
                      <ArrowDown />
                      {t("Down")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pending}
                      onClick={() => action("input", { text: "\n" })}
                    >
                      <CornerDownLeft />
                      Enter
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={pending}
                      onClick={() => action("input", { text: "\u0004" })}
                    >
                      EOF
                    </Button>
                  </div>
                </details>
              </div>
            </form>
          )}
        </section>
      )}
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle>{t("Run this operation?")}</DialogTitle>
          <DialogDescription className="mt-3">
            {t(
              "This command can change local data, settings or services. Review the command before continuing.",
            )}
          </DialogDescription>
          <pre className="confirmation-command">
            ygg {command} {args}
          </pre>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>
              {t("Cancel")}
            </Button>
            <Button onClick={() => start(true)}>{t("Run command")}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
