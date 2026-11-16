import { t, useI18n, formatNumber } from "../lib/i18n";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUp,
  BookOpen,
  Check,
  History,
  MessageSquare,
  Plus,
  RotateCcw,
  Square,
  Sprout,
  Trash2,
  User,
} from "lucide-react";
import type { Chat, Message, Scope } from "../lib/types";
import { readEvents, request, streamChat } from "../lib/api";
import { useResource } from "../lib/hooks";
import { excerpt, projectName, projectUrl } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Textarea } from "../components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import { ErrorNotice, Loading, SettingsLink } from "../components/common";
import type { Selection } from "../components/memory-detail";
export function ChatPage({
  project,
  chatId,
  onSelect,
}: {
  project: Scope;
  chatId?: string;
  onSelect: (s: Selection) => void;
}) {
  useI18n();
  const navigate = useNavigate();
  const list = useResource<{ chats: Chat[] }>("/api/chats/list", { project });
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [verified, setVerified] = useState(!chatId);
  const [loadVersion, setLoadVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [remove, setRemove] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sourceMessageId, setSourceMessageId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const sourceMessage =
    messages.find((m) => m.id === sourceMessageId && m.role === "assistant") ||
    [...messages].reverse().find((m) => m.role === "assistant");
  const [deleting, setDeleting] = useState(false);
  const active = useRef<{ id: string; controller: AbortController } | null>(
    null,
  );
  const alive = useRef(true);
  const generation = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);
  const url = (id?: string) =>
    project === null
      ? `/chat${id ? `?chat=${encodeURIComponent(id)}` : ""}`
      : projectUrl(project, "chat", id);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (active.current) {
        void request(
          `/api/chats/${encodeURIComponent(active.current.id)}/stop`,
          {},
        ).catch(() => {});
        active.current.controller.abort();
      }
    };
  }, []);
  useEffect(() => {
    if (active.current && active.current.id === chatId) return;
    generation.current++;
    if (active.current) {
      const old = active.current;
      active.current = null;
      old.controller.abort();
      void request(`/api/chats/${encodeURIComponent(old.id)}/stop`, {}).catch(
        () => {},
      );
    }
    setBusy(false);
    setPhase("");
    setError("");
    setMessages([]);
    setSourceMessageId(null);
    setSourcesOpen(true);
    setVerified(!chatId);
    setDraft("");
    if (!chatId) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    request<{ chat: Chat; messages: Message[] }>(
      `/api/chats/${encodeURIComponent(chatId)}`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (result.chat.project !== project)
          throw new Error(
            t(
              "This conversation belongs to another project. Open it from its workspace.",
            ),
          );
        if (!controller.signal.aborted) {
          setMessages(result.messages);
          setVerified(true);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [chatId, project, loadVersion]);
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "instant", block: "nearest" });
  }, [messages.length, busy]);
  async function send(content = draft) {
    if (!content.trim() || busy || loading || !verified) return;
    const controller = new AbortController();
    const run = ++generation.current;
    setBusy(true);
    setError("");
    setPhase("Searching memory…");
    setSourceMessageId(null);
    let id = chatId;
    let assistant: Message = {
      id: `pending-${Date.now()}`,
      role: "assistant",
      content: "",
      sources: [],
      status: "stopped",
      created_at: Date.now() / 1000,
    };
    try {
      if (!id) {
        const chat = await request<Chat>("/api/chats", { project });
        id = chat.id;
        if (!alive.current || run !== generation.current) return;
        active.current = { id, controller };
        navigate(url(id), { replace: true });
      } else active.current = { id, controller };
      setDraft("");
      setMessages((current) => [
        ...current,
        {
          id: `user-${Date.now()}`,
          role: "user",
          content: content.trim(),
          sources: [],
          status: "complete",
          created_at: Date.now() / 1000,
        },
        assistant,
      ]);
      let terminal = false;
      for await (const event of readEvents(
        await streamChat(id, content.trim(), controller.signal),
      )) {
        if (!alive.current || run !== generation.current) break;
        if (event.type === "sources") {
          assistant = {
            ...assistant,
            sources: event.sources,
            truncated: event.truncated,
          };
          setPhase("Preparing an answer…");
        } else if (event.type === "delta") {
          assistant = { ...assistant, content: assistant.content + event.text };
          setPhase("Answering…");
        } else if (event.type === "done") {
          assistant = event.message;
          terminal = true;
        } else {
          assistant = event.message || { ...assistant, status: "error" };
          setError(event.error);
          terminal = true;
        }
        setMessages((current) => [...current.slice(0, -1), assistant]);
      }
      if (!terminal && !controller.signal.aborted)
        throw new Error(
          t("Connection interrupted. The answer was only partially saved."),
        );
    } catch (e) {
      if (alive.current && run === generation.current) {
        const stopped = controller.signal.aborted;
        setMessages((current) =>
          current.map((m) =>
            m.id === assistant.id
              ? { ...m, status: stopped ? "stopped" : "error" }
              : m,
          ),
        );
        if (!stopped) setError((e as Error).message);
      }
    } finally {
      if (alive.current && run === generation.current) {
        setBusy(false);
        setPhase("");
        list.reload();
        active.current = null;
      }
    }
  }
  async function stop() {
    if (!active.current) return;
    try {
      await request(
        `/api/chats/${encodeURIComponent(active.current.id)}/stop`,
        {},
      );
      active.current?.controller.abort();
      setPhase("Stopping…");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function deleteChat() {
    if (!chatId) return;
    setDeleting(true);
    try {
      await request(
        `/api/chats/${encodeURIComponent(chatId)}`,
        undefined,
        "DELETE",
      );
      setRemove(false);
      navigate(url());
      list.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  }
  const history = (
    <>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("Conversations")}</h3>
        <Button
          variant="ghost"
          size="icon"
          disabled={busy}
          aria-label={t("New conversation")}
          onClick={() => {
            navigate(url());
            setHistoryOpen(false);
          }}
        >
          <Plus />
        </Button>
      </div>
      {list.error ? (
        <ErrorNotice error={list.error} retry={list.reload} />
      ) : list.loading ? (
        <p className="mt-4 text-sm text-muted-foreground">{t("Loading…")}</p>
      ) : list.value?.chats.length ? (
        <div className="mt-3 space-y-1">
          {list.value.chats.map((chat) => (
            <button
              key={chat.id}
              disabled={busy}
              className={`chat-history-item ${chat.id === chatId ? "active" : ""}`}
              onClick={() => {
                navigate(url(chat.id));
                setHistoryOpen(false);
              }}
            >
              <MessageSquare size={15} />
              <span>{chat.title || t("New conversation")}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm leading-6 text-muted-foreground">
          {t("Your conversations with memory will appear here.")}
        </p>
      )}
    </>
  );
  return (
    <div className="chat-layout">
      <aside className="chat-history">{history}</aside>
      <section className="chat-main">
        <div className="chat-topline">
          <div className="flex min-w-0 items-center gap-2">
            <span className="scope-pill">
              <span className="status-dot" />
              {projectName(project)}
            </span>
            <span className="hidden text-xs text-muted-foreground xl:block">
              {t("Answers grounded in your memory")}
            </span>
          </div>
          <div className="flex">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label={t("Conversation history")}
              onClick={() => setHistoryOpen(true)}
            >
              <History />
            </Button>
            {chatId && (
              <Button
                variant="ghost"
                size="icon"
                disabled={busy}
                aria-label={t("Delete conversation")}
                onClick={() => setRemove(true)}
              >
                <Trash2 />
              </Button>
            )}
          </div>
        </div>
        <div className="chat-messages">
          {loading ? (
            <Loading label={t("Opening conversation…")} />
          ) : messages.length === 0 && !error ? (
            <div className="chat-welcome">
              <div className="chat-welcome-mark">
                <Sprout size={35} />
              </div>
              <h2>
                {project === null
                  ? t("What shall we ask your memory?")
                  : t("What would you like to know about {name}?", {
                      name: projectName(project),
                    })}
              </h2>
              <p>
                {project === null
                  ? t(
                      "Find an answer in one project or connect experience across several.",
                    )
                  : t("Answers will use only this project’s knowledge.")}
              </p>
              <div className="suggestion-grid">
                {[
                  t("What key decisions have we made?"),
                  t("What questions remain open?"),
                  t("What lessons should we keep in mind?"),
                ].map((text) => (
                  <button
                    key={text}
                    className="suggestion"
                    onClick={() => setDraft(text)}
                  >
                    {text}
                    <ArrowUp size={15} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <article key={message.id} className={`message ${message.role}`}>
                <div className="message-author">
                  {message.role === "user" ? (
                    <User size={16} />
                  ) : (
                    <Sprout size={17} />
                  )}
                  <span>
                    {message.role === "user" ? t("You") : "Yggdrasil"}
                  </span>
                  {message.role === "assistant" &&
                    message.status === "complete" && (
                      <Check size={13} className="text-primary" />
                    )}
                </div>
                <div className="message-content">
                  {message.content ? (
                    renderContent(message, onSelect)
                  ) : busy && index === messages.length - 1 ? (
                    <span className="text-muted-foreground">{t(phase)}</span>
                  ) : null}
                </div>
                {message.role === "assistant" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="message-source-toggle"
                    aria-pressed={sourceMessage?.id === message.id}
                    onClick={() => {
                      setSourceMessageId(message.id);
                      setSourcesOpen(true);
                    }}
                  >
                    <BookOpen size={13} />
                    {t("Sources ({count})", { count: message.sources.length })}
                  </Button>
                )}
                {message.truncated && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    {t("Context was shortened to fit the model’s capacity.")}
                  </p>
                )}
                {message.status === "search_only" &&
                  message.sources.length > 0 && (
                    <div className="mt-3">
                      <p className="mb-2 text-sm text-muted-foreground">
                        {t(
                          "Matching knowledge is shown. Connect a model to generate an answer.",
                        )}
                      </p>
                      <SettingsLink />
                    </div>
                  )}
                {message.role === "assistant" &&
                  (message.status === "error" ||
                    message.status === "stopped") &&
                  !busy && (
                    <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        {message.status === "stopped"
                          ? t("Answer stopped")
                          : t("Answer incomplete")}
                      </span>
                      {index > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => send(messages[index - 1].content)}
                        >
                          <RotateCcw />
                          {t("Retry")}
                        </Button>
                      )}
                    </div>
                  )}
              </article>
            ))
          )}
          {error && (
            <ErrorNotice
              error={error}
              retry={!verified ? () => setLoadVersion((v) => v + 1) : undefined}
            />
          )}
          <div ref={bottom} />
        </div>
        <form
          className="chat-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label className="sr-only" htmlFor="chat-question">
            {t("Your question")}
          </label>
          <Textarea
            id="chat-question"
            placeholder={
              project === null
                ? t("Ask about any project…")
                : t("Ask about this project…")
            }
            value={draft}
            maxLength={8000}
            disabled={busy || loading || !verified}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <div className="composer-bottom">
            <span>
              {busy ? (
                <span role="status">{t(phase)}</span>
              ) : (
                <>
                  {t("Enter — send")}{" "}
                  <span className="hidden sm:inline">
                    {t("· Shift + Enter — new line")}
                  </span>
                </>
              )}
            </span>
            {busy ? (
              <Button
                type="button"
                size="icon"
                variant="secondary"
                aria-label={t("Stop answer")}
                onClick={stop}
              >
                <Square />
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                disabled={!draft.trim() || loading || !verified}
                aria-label={t("Send question")}
              >
                <ArrowUp />
              </Button>
            )}
          </div>
        </form>
        <p className="chat-footnote">
          {t(
            "Verify important conclusions against sources. Chat does not change project memory.",
          )}
        </p>
      </section>
      <aside
        className={`chat-sources ${sourcesOpen ? "is-open" : ""}`}
        aria-label={t("Response sources")}
      >
        <button
          className="chat-sources-heading"
          type="button"
          aria-expanded={sourcesOpen}
          aria-controls="chat-sources-list"
          onClick={() => setSourcesOpen(!sourcesOpen)}
        >
          <BookOpen size={16} />
          <span>{t("Response sources")}</span>
          <span>{formatNumber(sourceMessage?.sources.length || 0)}</span>
        </button>
        <div id="chat-sources-list" className="chat-sources-list">
          {sourceMessage?.sources.length ? (
            sourceMessage.sources.map((source, i) => (
              <button
                key={`${source.id}:${i}`}
                className="chat-source-card"
                onClick={() =>
                  onSelect({ id: source.id, project: source.project })
                }
              >
                <span className="source-number">{formatNumber(i + 1)}</span>
                <span className="min-w-0">
                  <strong>{projectName(source.project)}</strong>
                  <span>{excerpt(source.content, 220)}</span>
                </span>
              </button>
            ))
          ) : (
            <p className="chat-sources-empty">
              {t("No sources for this response.")}
            </p>
          )}
        </div>
      </aside>
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent sheet>
          <DialogTitle className="mb-6">{t("Chat history")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("Conversations in this workspace")}
          </DialogDescription>
          {history}
        </DialogContent>
      </Dialog>
      <Dialog open={remove} onOpenChange={setRemove}>
        <DialogContent>
          <DialogTitle>{t("Delete this conversation?")}</DialogTitle>
          <DialogDescription className="mt-3">
            {t(
              "Messages will be deleted from this device. Memory records will remain.",
            )}
          </DialogDescription>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRemove(false)}>
              {t("Cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={deleteChat}
            >
              {deleting ? t("Deleting…") : t("Delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
function renderContent(message: Message, onSelect: (s: Selection) => void) {
  const content =
    message.role === "assistant" && message.status === "search_only"
      ? t(
          message.sources.length
            ? "Matching records were found. Connect a model in settings to answer using them."
            : "No matching memory was found. Refine your question or add knowledge to this project.",
        )
      : message.content;
  return content.split(/(\[\d+\])/g).map((part, i) => {
    const match = /^\[(\d+)\]$/.exec(part);
    const source = match ? message.sources[Number(match[1]) - 1] : undefined;
    return source ? (
      <button
        className="citation"
        key={i}
        onClick={() => onSelect({ id: source.id, project: source.project })}
        aria-label={t("Source {number}: {name}", {
          number: Number(match![1]),
          name: projectName(source.project),
        })}
      >
        {part}
      </button>
    ) : (
      part
    );
  });
}
