import { UI_VERSION, WORKSPACE_FEATURES } from "./lib/features";
import { useRelease } from "./lib/releases";
import {
  VersionBadge,
  GitHubButton,
  UpdateDialog,
} from "./components/release-controls";
import { Toaster } from "./components/ui/sonner";
import { t, useI18n, LanguagePicker, formatNumber } from "./lib/i18n";
import { useTheme } from "./lib/theme";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  ChevronRight,
  FolderOpen,
  Menu,
  MessageSquare,
  Moon,
  Network,
  Settings,
  SlidersHorizontal,
  FileText,
  Sprout,
  Sun,
} from "lucide-react";
import type { Project } from "./lib/types";
import { useResource } from "./lib/hooks";
import { request } from "./lib/api";
import { cn, projectName, projectUrl } from "./lib/utils";
import { Projects } from "./pages/projects";
import { Overview, Knowledge, Sources } from "./pages/knowledge";
import { ChatPage } from "./pages/chat";
import { SettingsPage } from "./pages/settings";
import { OperationsPage } from "./pages/operations";
import { MemoryDetail, type Selection } from "./components/memory-detail";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import { Empty, ErrorNotice, Loading } from "./components/common";
const GraphPage = lazy(() =>
  import("./pages/graph").then((m) => ({ default: m.GraphPage })),
);
export function App({
  status,
}: {
  status: { engine: boolean; user_id: string; namespace: string };
}) {
  useI18n();
  const release = useRelease();
  const projects = useResource<{ projects: Project[] }>("/api/projects");
  const [engineConnected, setEngineConnected] = useState(status.engine);
  useEffect(() => {
    let active = true;
    const refresh = () => {
      projects.reload();
      void request<{ engine: boolean }>("/api/status")
        .then((value) => {
          if (active) setEngineConnected(value.engine);
        })
        .catch(() => {
          if (active) setEngineConnected(false);
        });
    };
    window.addEventListener("ygg-data-changed", refresh);
    return () => {
      active = false;
      window.removeEventListener("ygg-data-changed", refresh);
    };
  }, [projects.reload]);

  const [selection, setSelection] = useState<Selection | null>(null);
  const [mobile, setMobile] = useState(false);
  const { theme, setTheme } = useTheme();
  const dark = theme.mode === "dark";
  const location = useLocation();
  const currentProject = new URLSearchParams(location.search).get("project");
  useEffect(() => {
    setMobile(false);
    setSelection(null);
  }, [location.pathname, location.search]);
  const sidebar = (
    <>
      <Link to="/" className="brand">
        <span className="brand-icon">
          <Sprout size={25} />
        </span>
        <span>
          Yggdrasil
          <span className="brand-subtitle">{t("Knowledge workspace")}</span>
        </span>
      </Link>
      <div className="sidebar-release">
        <VersionBadge release={release} />
        <GitHubButton release={release} />
      </div>
      <span className="workspace-preview-badge">
        UI {UI_VERSION}
        <span aria-hidden="true">·</span>
        {t("Experimental")}
      </span>
      <nav aria-label={t("Main navigation")} className="main-nav">
        <NavLink
          end
          to="/"
          className={({ isActive }) => cn("nav-item", isActive && "active")}
        >
          <FolderOpen size={18} />
          {t("Projects")}
        </NavLink>
        {WORKSPACE_FEATURES.chat && (
          <NavLink
            to="/chat"
            className={({ isActive }) => cn("nav-item", isActive && "active")}
          >
            <MessageSquare size={18} />
            {t("Global chat")}
          </NavLink>
        )}
      </nav>
      <div className="sidebar-project-heading">
        {t("Projects")}
        <span>{formatNumber(projects.value?.projects.length || 0)}</span>
      </div>
      <nav className="project-nav" aria-label={t("Projects")}>
        {projects.value?.projects.map((p) => (
          <Link
            key={p.name}
            to={projectUrl(p.name)}
            className={cn(
              "nav-project",
              location.pathname === "/project" &&
                currentProject === p.name &&
                "active",
            )}
          >
            <span className="project-dot" />
            <span className="truncate">{projectName(p.name)}</span>
            <span className="project-nav-count">{formatNumber(p.count)}</span>
          </Link>
        ))}
        {!projects.loading && !projects.value?.projects.length && (
          <p className="px-3 text-xs leading-6 text-[var(--sidebar-muted)]">
            {t("Your projects will appear here after you add knowledge.")}
          </p>
        )}
      </nav>
      <div className="sidebar-bottom">
        <NavLink
          to="/operations"
          className={({ isActive }) => cn("nav-item", isActive && "active")}
        >
          <SlidersHorizontal size={18} />
          {t("Operations")}
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) => cn("nav-item", isActive && "active")}
        >
          <Settings size={18} />
          {t("Settings")}
        </NavLink>
        <div className="sidebar-status">
          <span className={cn("status-dot", !engineConnected && "offline")} />
          <div>
            <p>
              {engineConnected
                ? t("Memory connected")
                : t("Engine unavailable")}
            </p>
            <span>{status.namespace}</span>
          </div>
          <span className="local-label">{t("Local")}</span>
        </div>
      </div>
    </>
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        {t("Skip to content")}
      </a>
      <aside className="sidebar">{sidebar}</aside>
      <div className="workspace">
        <header className="topbar">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              className="lg:hidden"
              variant="ghost"
              size="icon"
              aria-label={t("Open navigation")}
              onClick={() => setMobile(true)}
            >
              <Menu />
            </Button>
            <span className="text-sm text-muted-foreground hidden sm:inline">
              {t("My workspace")}
            </span>
            <ChevronRight
              size={14}
              className="hidden sm:block text-muted-foreground"
            />
            <span className="truncate text-sm font-medium">
              {location.pathname === "/project"
                ? projectName(currentProject)
                : location.pathname === "/chat"
                  ? t("Global chat")
                  : location.pathname === "/settings"
                    ? t("Settings")
                    : location.pathname === "/operations"
                      ? t("Operations")
                      : t("Projects")}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
              {t("On your device")}
              <span className="status-dot" aria-hidden="true" />
            </span>
            <LanguagePicker />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setTheme({ mode: dark ? "light" : "dark" })}
              aria-label={
                dark ? t("Switch to light theme") : t("Switch to dark theme")
              }
            >
              {dark ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>
        <main
          id="main"
          className={cn(
            "main-content",
            location.pathname === "/chat" && "global-chat-content",
          )}
        >
          <Routes>
            <Route
              path="/"
              element={
                <Projects
                  projects={projects.value?.projects || []}
                  loading={projects.loading}
                  error={projects.error}
                  reload={projects.reload}
                />
              }
            />
            <Route
              path="/project"
              element={
                <ProjectPage
                  projects={projects.value?.projects || []}
                  loading={projects.loading}
                  error={projects.error}
                  reload={projects.reload}
                  onSelect={setSelection}
                />
              }
            />
            <Route
              path="/chat"
              element={
                WORKSPACE_FEATURES.chat ? (
                  <GlobalChat onSelect={setSelection} />
                ) : (
                  <Navigate to="/" replace />
                )
              }
            />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route
              path="*"
              element={
                <Empty title={t("Page not found")}>
                  <Link className="text-primary underline" to="/">
                    {t("Back to projects")}
                  </Link>
                </Empty>
              }
            />
          </Routes>
        </main>
      </div>
      <Dialog open={mobile} onOpenChange={setMobile}>
        <DialogContent
          sheet
          className="left-0 right-auto max-w-72 bg-[var(--sidebar)] p-0 text-[var(--sidebar-foreground)]"
        >
          <DialogTitle className="sr-only">{t("Navigation")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("Projects, operations and settings")}
          </DialogDescription>
          <div className="mobile-sidebar">{sidebar}</div>
        </DialogContent>
      </Dialog>
      <Toaster />
      <UpdateDialog release={release} />
      <MemoryDetail
        selection={selection}
        onClose={() => setSelection(null)}
        onSelect={setSelection}
      />
    </div>
  );
}
function GlobalChat({ onSelect }: { onSelect: (s: Selection) => void }) {
  useI18n();
  const [params] = useSearchParams();
  return (
    <>
      <header className="page-heading compact">
        <h1>{t("Global chat")}</h1>
        <p>{t("Ask the memory across all your projects.")}</p>
      </header>
      <ChatPage
        project={null}
        chatId={params.get("chat") || undefined}
        onSelect={onSelect}
      />
    </>
  );
}
const tabs = [
  ["overview", "Overview", SlidersHorizontal],
  ["knowledge", "Knowledge", BookOpen],
  ["sources", "Sources", FileText],
  ["graph", "Graph", Network],
  ["chat", "Chat", MessageSquare],
] as const;
const visibleTabs = tabs.filter(
  ([name]) =>
    (name !== "chat" || WORKSPACE_FEATURES.chat) &&
    (name !== "graph" || WORKSPACE_FEATURES.graph),
);
function ProjectPage({
  projects,
  loading,
  error,
  reload,
  onSelect,
}: {
  projects: Project[];
  loading: boolean;
  error: string;
  reload: () => void;
  onSelect: (s: Selection) => void;
}) {
  useI18n();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const name = params.get("project") ?? "";
  const tab = visibleTabs.some((t) => t[0] === params.get("tab"))
    ? params.get("tab")!
    : "overview";
  const project = projects.find((p) => p.name === name);
  const onTab = (value: string) => navigate(projectUrl(name, value));
  if (loading) return <Loading />;
  if (error) return <ErrorNotice error={error} retry={reload} />;
  if (!project)
    return (
      <Empty title={t("Project not found")}>
        {t("This workspace has no records for this project.")}{" "}
        <Link className="text-primary underline" to="/">
          {t("All projects")}
        </Link>
      </Empty>
    );
  return (
    <>
      <Link to="/" className="back-link">
        <ArrowLeft size={14} />
        {t("All projects")}
      </Link>
      <header className="project-heading">
        <div>
          <div className="flex items-center gap-3">
            <div className="project-symbol">
              <Sprout size={25} />
            </div>
            <h1>{projectName(name)}</h1>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {t("{count} memories · {types} knowledge types", {
              count: project.count,
              types: Object.keys(project.types).length,
            })}
            {project.archived_count
              ? t(" · {count} archived", { count: project.archived_count })
              : ""}
          </p>
        </div>
        {WORKSPACE_FEATURES.chat && tab !== "chat" && (
          <Button onClick={() => onTab("chat")}>
            <MessageSquare />
            {t("Ask about this project")}
          </Button>
        )}
      </header>
      <Tabs value={tab} onValueChange={onTab}>
        <TabsList aria-label={t("Project sections")}>
          {visibleTabs.map(([value, label, Icon]) => (
            <TabsTrigger key={value} value={value}>
              <Icon size={16} />
              {t(label)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent
          value={tab}
          className="project-tab-content"
          key={`${name}:${tab}`}
          aria-label={t(tabs.find((tabItem) => tabItem[0] === tab)?.[1] || "")}
        >
          {tab === "overview" ? (
            <Overview project={project} onSelect={onSelect} onTab={onTab} />
          ) : tab === "knowledge" ? (
            <Knowledge
              key={
                params.has("source") ? `source:${params.get("source")}` : "all"
              }
              project={project}
              onSelect={onSelect}
              sourcePreset={params.get("source") ?? undefined}
            />
          ) : tab === "sources" ? (
            <Sources
              project={name}
              onSource={(source) =>
                navigate(
                  `${projectUrl(name, "knowledge")}&source=${encodeURIComponent(source)}`,
                )
              }
            />
          ) : tab === "graph" ? (
            <Suspense fallback={<Loading />}>
              <GraphPage project={project} onSelect={onSelect} />
            </Suspense>
          ) : (
            <ChatPage
              project={name}
              chatId={params.get("chat") || undefined}
              onSelect={onSelect}
            />
          )}
        </TabsContent>
      </Tabs>
    </>
  );
}
