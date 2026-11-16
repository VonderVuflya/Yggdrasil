import { WORKSPACE_FEATURES } from "../lib/features";
import { t, useI18n, formatNumber } from "../lib/i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  LayoutGrid,
  List,
  MessageSquare,
  BookOpen,
  Search,
  Sprout,
} from "lucide-react";
import type { Project } from "../lib/types";
import { date, projectName, projectUrl, typeName } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge, Empty, ErrorNotice, Loading } from "../components/common";
export function TreeMark({ className = "" }: { className?: string }) {
  useI18n();
  return (
    <svg
      className={className}
      viewBox="0 0 360 240"
      fill="none"
      aria-hidden="true"
    >
      <g stroke="currentColor" strokeWidth="1.5">
        <path d="M180 221V124M180 164L101 109V63M180 139L249 95V36M180 124V39M101 89L57 57M249 76L294 47M180 186L272 150L310 105M180 203L84 162L44 124M180 87L142 62M180 113L216 64" />
        <path d="M180 221L133 234M180 221L213 237" opacity=".4" />
      </g>
      {[
        [180, 39],
        [142, 62],
        [216, 64],
        [249, 36],
        [294, 47],
        [101, 63],
        [57, 57],
        [310, 105],
        [44, 124],
        [84, 162],
        [272, 150],
        [180, 124],
      ].map(([x, y], i) => (
        <g key={i}>
          <circle
            cx={x}
            cy={y}
            r={i === 11 ? 13 : 7}
            fill="currentColor"
            opacity={i === 11 ? ".2" : ".09"}
          />
          <circle cx={x} cy={y} r={i === 11 ? 5 : 3} fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}
export function Projects({
  projects,
  loading,
  error,
  reload,
}: {
  projects: Project[];
  loading: boolean;
  error: string;
  reload: () => void;
}) {
  useI18n();
  const [query, setQuery] = useState("");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const filtered = projects.filter((p) =>
    projectName(p.name).toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const count = projects.reduce((n, p) => n + p.count, 0);
  return (
    <div className="page-enter">
      <section className="projects-hero">
        <div className="relative z-10 max-w-xl">
          <div className="inline-flex items-center gap-2 text-sm font-medium text-primary">
            <Sprout size={18} />
            {t("Your knowledge workspace")}
          </div>
          <h1 className="mt-4">
            {t("Everything you know.")}
            <br />
            {t("Connected.")}
          </h1>
          <p className="mt-4 max-w-lg text-muted-foreground leading-7">
            {t(
              "Revisit decisions, browse sources and bring new knowledge into your projects.",
            )}
          </p>
          <Button asChild className="mt-6">
            <Link to={WORKSPACE_FEATURES.chat ? "/chat" : "/operations"}>
              {WORKSPACE_FEATURES.chat ? <MessageSquare /> : <Sprout />}
              {t(
                WORKSPACE_FEATURES.chat
                  ? "Ask across all projects"
                  : "Import knowledge",
              )}
              <ArrowUpRight />
            </Link>
          </Button>
        </div>
        <TreeMark className="hero-tree" />
      </section>
      <div className="section-heading">
        <div>
          <h2>
            {t("Your projects")}{" "}
            <span className="heading-count">
              {formatNumber(projects.length)}
            </span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("{count} memories in total", { count })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="search-icon" />
            <Input
              className="pl-10 w-full sm:w-60"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label={t("Find a project")}
              placeholder={t("Find a project…")}
            />
          </div>
          <div className="segmented">
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("Cards")}
              aria-pressed={layout === "grid"}
              onClick={() => setLayout("grid")}
            >
              <LayoutGrid />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("List")}
              aria-pressed={layout === "list"}
              onClick={() => setLayout("list")}
            >
              <List />
            </Button>
          </div>
        </div>
      </div>
      {error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : loading ? (
        <Loading />
      ) : filtered.length === 0 ? (
        <Empty
          title={query ? t("No projects found") : t("Your memory starts here")}
        >
          {query
            ? t("Try a different name.")
            : t("Save knowledge from work conversations using")}{" "}
          {!query && <code>ygg seed</code>}
        </Empty>
      ) : (
        <div className={layout === "grid" ? "project-grid" : "project-list"}>
          {filtered.map((project, index) => (
            <article key={project.name} className="project-card">
              <div className="flex items-center justify-between">
                <div className={`project-symbol symbol-${index % 4}`}>
                  <Sprout size={23} />
                </div>
                <span className="text-xs text-muted-foreground">
                  {date(project.latest_at)}
                </span>
              </div>
              <Link
                className="project-title"
                to={projectUrl(project.name)}
                aria-label={t("Open project {name}", {
                  name: projectName(project.name),
                })}
              >
                {projectName(project.name)}
                <ArrowUpRight size={18} />
              </Link>
              <p className="text-sm text-muted-foreground">
                {t("{count} memories", { count: project.count })}
                {project.archived_count > 0
                  ? t(" · {count} archived", { count: project.archived_count })
                  : ""}
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                {Object.entries(project.types)
                  .slice(0, 3)
                  .map(([type, n]) => (
                    <Badge key={type}>
                      {typeName(type)}{" "}
                      <span className="opacity-65">{formatNumber(n)}</span>
                    </Badge>
                  ))}
              </div>
              <div className="project-card-footer">
                <Link
                  className="inline-flex items-center gap-2 text-sm font-semibold text-primary"
                  to={projectUrl(
                    project.name,
                    WORKSPACE_FEATURES.chat ? "chat" : "knowledge",
                  )}
                  aria-label={t(
                    WORKSPACE_FEATURES.chat
                      ? "Ask about {name}"
                      : "Browse knowledge in {name}",
                    {
                      name: projectName(project.name),
                    },
                  )}
                >
                  {WORKSPACE_FEATURES.chat ? (
                    <MessageSquare size={15} />
                  ) : (
                    <BookOpen size={15} />
                  )}
                  {t(
                    WORKSPACE_FEATURES.chat
                      ? "Ask a question"
                      : "Browse knowledge",
                  )}
                </Link>
                <span className="tiny-branch" aria-hidden="true">
                  ⌁
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="local-note">
        <span className="status-dot" />
        {t("Data is stored on this device. Your knowledge stays yours.")}
      </div>
    </div>
  );
}
