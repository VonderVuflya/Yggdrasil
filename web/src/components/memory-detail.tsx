import { WORKSPACE_FEATURES } from "../lib/features";
import { t, useI18n } from "../lib/i18n";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, MessageSquare } from "lucide-react";
import type { Memory, Edge, Scope, Chat } from "../lib/types";
import { useResource } from "../lib/hooks";
import { request } from "../lib/api";
import { date, projectName, projectUrl, typeName } from "../lib/utils";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Badge, ErrorNotice, Loading } from "./common";
export type Selection = { id: string; project: Scope };
export function MemoryDetail({
  selection,
  onClose,
  onSelect,
}: {
  selection: Selection | null;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
}) {
  useI18n();
  return (
    <Dialog
      open={!!selection}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      {selection && (
        <DialogContent sheet>
          <Detail
            key={selection.id}
            selection={selection}
            onClose={onClose}
            onSelect={onSelect}
          />
        </DialogContent>
      )}
    </Dialog>
  );
}
function Detail({
  selection,
  onClose,
  onSelect,
}: {
  selection: Selection;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
}) {
  useI18n();
  const { value, loading, error, reload } = useResource<{
    memory: Memory;
    relations: Edge[];
  }>("/api/memory", selection);
  const navigate = useNavigate();
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  async function discuss() {
    if (!value) return;
    setBusy(true);
    try {
      const chat = await request<Chat>("/api/chats", {
        project: value.memory.project,
        memory_id: value.memory.id,
      });
      onClose();
      navigate(projectUrl(value.memory.project, "chat", chat.id));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="mb-7 pr-8">
        <div className="detail-icon">
          <FileText size={22} />
        </div>
        <DialogTitle className="mt-4">{t("Memory record")}</DialogTitle>
        <DialogDescription className="mt-2">
          {t("Saved knowledge and its origins")}
        </DialogDescription>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : (
        value && (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge>{typeName(value.memory.type)}</Badge>
              <Badge>{projectName(value.memory.project)}</Badge>
              {value.memory.archived && <Badge>{t("Archive")}</Badge>}
            </div>
            <p className="mt-6 whitespace-pre-wrap break-words text-base leading-8">
              {value.memory.content}
            </p>
            <dl className="detail-metadata">
              <dt>{t("Saved")}</dt>
              <dd>{date(value.memory.created_at)}</dd>
              <dt>{t("Source")}</dt>
              <dd className="break-anywhere">
                {value.memory.source || t("Not specified")}
              </dd>
              <dt>{t("Identifier")}</dt>
              <dd className="break-anywhere font-mono text-xs">
                {value.memory.id}
              </dd>
            </dl>
            {value.relations.length > 0 && (
              <section className="mt-6">
                <h3 className="font-semibold">{t("Connections")}</h3>
                <ul className="mt-3 space-y-2">
                  {value.relations.map((edge, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-border p-3 text-sm"
                    >
                      <span className="font-medium">{edge.rel_type}</span>
                      <p className="mt-1 text-muted-foreground break-anywhere">
                        {edge.from_id === selection.id
                          ? edge.to_id
                          : edge.from_id}
                      </p>
                      {!edge.external && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2"
                          onClick={() =>
                            onSelect({
                              id:
                                edge.from_id === selection.id
                                  ? edge.to_id
                                  : edge.from_id,
                              project: value.memory.project,
                            })
                          }
                        >
                          {t("Open linked record")}
                        </Button>
                      )}
                      {edge.external && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2"
                          onClick={() => {
                            onClose();
                            navigate(projectUrl(edge.other_project || ""));
                          }}
                        >
                          {t("Open project")}
                          {projectName(edge.other_project || "")}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <details className="mt-6 text-sm">
              <summary className="cursor-pointer text-muted-foreground">
                {t("All metadata")}
              </summary>
              <pre className="mt-3 whitespace-pre-wrap break-anywhere rounded-lg bg-muted p-3 text-xs">
                {JSON.stringify(value.memory.metadata, null, 2)}
              </pre>
            </details>
            {actionError && <ErrorNotice error={actionError} />}
            {WORKSPACE_FEATURES.chat && (
              <Button className="mt-8 w-full" disabled={busy} onClick={discuss}>
                <MessageSquare />
                {busy ? t("Opening conversation…") : t("Discuss in chat")}
              </Button>
            )}
          </>
        )
      )}
    </>
  );
}
