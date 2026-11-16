import { WORKSPACE_FEATURES } from "../lib/features";
import { t, useI18n, formatNumber } from "../lib/i18n";
import { useState } from "react";
import { ArrowLeft, ArrowRight, FileText, Search } from "lucide-react";
import type { Memory, Project } from "../lib/types";
import { useDebounced, useResource } from "../lib/hooks";
import { date, excerpt, typeName } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge, Empty, ErrorNotice, Loading } from "../components/common";
import type { Selection } from "../components/memory-detail";
export function MemoryRow({
  memory,
  onSelect,
}: {
  memory: Memory;
  onSelect: (selection: Selection) => void;
}) {
  useI18n();
  return (
    <button
      className="memory-row"
      onClick={() => onSelect({ id: memory.id, project: memory.project })}
    >
      <div className="memory-icon">
        <FileText size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge>{typeName(memory.type)}</Badge>
          {memory.archived && <Badge>{t("Archive")}</Badge>}
          <span className="text-xs text-muted-foreground">
            {date(memory.created_at)}
          </span>
        </div>
        <p className="leading-6">{excerpt(memory.content, 240)}</p>
        {memory.source && (
          <p className="mt-2 truncate text-xs text-muted-foreground">
            {memory.source}
          </p>
        )}
      </div>
      <ArrowRight size={17} className="mt-2 shrink-0 text-muted-foreground" />
    </button>
  );
}
export function Knowledge({
  project,
  onSelect,
  sourcePreset,
}: {
  project: Project;
  onSelect: (s: Selection) => void;
  sourcePreset?: string;
}) {
  useI18n();
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [source, setSource] = useState(sourcePreset);
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const search = useDebounced(query);
  const resource = useResource<{ items: Memory[]; total: number }>(
    "/api/memories",
    {
      project: project.name,
      query: search,
      type,
      source,
      archived,
      offset,
      limit: 20,
    },
  );
  const sources = useResource<{ sources: { name: string; count: number }[] }>(
    "/api/sources",
    { project: project.name },
  );
  return (
    <>
      <div className="filter-toolbar">
        <div className="relative min-w-48 flex-1">
          <Search className="search-icon" />
          <Input
            className="pl-10"
            aria-label={t("Search knowledge")}
            placeholder={t("Search this project’s knowledge…")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
          />
        </div>
        <select
          aria-label={t("Record type")}
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">{t("All types")}</option>
          {Object.keys(project.types).map((t) => (
            <option value={t} key={t}>
              {typeName(t)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("Source")}
          value={source === undefined ? "__all_sources__" : source}
          onChange={(e) => {
            setSource(
              e.target.value === "__all_sources__" ? undefined : e.target.value,
            );
            setOffset(0);
          }}
        >
          <option value="__all_sources__">{t("All sources")}</option>
          {sources.value?.sources.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name || t("Source not specified")}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => {
              setArchived(e.target.checked);
              setOffset(0);
            }}
          />
          {t("Archive")}
        </label>
      </div>
      {resource.error ? (
        <ErrorNotice error={resource.error} retry={resource.reload} />
      ) : resource.loading ? (
        <Loading />
      ) : resource.value?.items.length ? (
        <>
          <div className="memory-list">
            {resource.value.items.map((m) => (
              <MemoryRow key={m.id} memory={m} onSelect={onSelect} />
            ))}
          </div>
          <div className="pagination">
            <span>
              {t("{start}–{end} of {total}", {
                start: offset + 1,
                end: Math.min(offset + 20, resource.value.total),
                total: resource.value.total,
              })}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 20))}
                aria-label={t("Previous page")}
              >
                <ArrowLeft />
              </Button>
              <Button
                variant="outline"
                size="icon"
                disabled={offset + 20 >= resource.value.total}
                onClick={() => setOffset(offset + 20)}
                aria-label={t("Next page")}
              >
                <ArrowRight />
              </Button>
            </div>
          </div>
        </>
      ) : (
        <Empty title={t("No records found")}>
          {t("Change your search or filters.")}
        </Empty>
      )}
    </>
  );
}
export function Overview({
  project,
  onSelect,
  onTab,
}: {
  project: Project;
  onSelect: (s: Selection) => void;
  onTab: (t: string) => void;
}) {
  useI18n();
  const recent = useResource<{ items: Memory[]; total: number }>(
    "/api/memories",
    { project: project.name, limit: 6, archived: false },
  );
  return (
    <div className="overview-layout">
      <section>
        <div className="section-heading compact">
          <h2>{t("Recent records")}</h2>
          <Button variant="ghost" size="sm" onClick={() => onTab("knowledge")}>
            {t("All knowledge")}
            <ArrowRight />
          </Button>
        </div>
        {recent.loading ? (
          <Loading />
        ) : recent.error ? (
          <ErrorNotice error={recent.error} retry={recent.reload} />
        ) : recent.value?.items.length ? (
          <div className="memory-list">
            {recent.value.items.map((m) => (
              <MemoryRow key={m.id} memory={m} onSelect={onSelect} />
            ))}
          </div>
        ) : (
          <Empty title={t("No active records yet")}>
            {t("Check the archive or save new knowledge using the CLI.")}
          </Empty>
        )}
      </section>
      <aside className="overview-aside">
        <div className="info-panel">
          <h3>{t("What your memory contains")}</h3>
          <div className="mt-5 space-y-4">
            {Object.entries(project.types).map(([type, count]) => (
              <div key={type}>
                <div className="flex justify-between gap-3 text-sm">
                  <span>{typeName(type)}</span>
                  <span className="font-semibold tabular-nums">
                    {formatNumber(count)}
                  </span>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/70"
                    style={{
                      width: `${Math.max(2, (100 * count) / Math.max(1, project.count))}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="info-panel graph-prompt">
          <h3>
            {t(
              WORKSPACE_FEATURES.graph
                ? "Knowledge connects"
                : "Know where it came from",
            )}
          </h3>
          <p>
            {t(
              WORKSPACE_FEATURES.graph
                ? "See which decisions complement each other and which have been revised."
                : "Follow each record back to its source and keep the original context at hand.",
            )}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() =>
              onTab(WORKSPACE_FEATURES.graph ? "graph" : "sources")
            }
          >
            {t(WORKSPACE_FEATURES.graph ? "Explore graph" : "Browse sources")}
            <ArrowRight />
          </Button>
        </div>
      </aside>
    </div>
  );
}
export function Sources({
  project,
  onSource,
}: {
  project: string;
  onSource: (name: string) => void;
}) {
  useI18n();
  const { value, loading, error, reload } = useResource<{
    sources: { name: string; count: number }[];
  }>("/api/sources", { project });
  return (
    <>
      <div className="section-heading compact">
        <div>
          <h2>{t("Knowledge sources")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("Origins of saved records")}
          </p>
        </div>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : value?.sources.length ? (
        <div className="memory-list">
          {value.sources.map((s) => (
            <button
              key={s.name}
              className="memory-row items-center"
              onClick={() => onSource(s.name)}
            >
              <div className="memory-icon">
                <FileText size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="break-anywhere font-medium">
                  {s.name || t("Source not specified")}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("{count} memories", { count: s.count })}
                </p>
              </div>
              <ArrowRight size={18} />
            </button>
          ))}
        </div>
      ) : (
        <Empty title={t("No sources yet")}>
          {t("They will appear with memory records.")}
        </Empty>
      )}
    </>
  );
}
