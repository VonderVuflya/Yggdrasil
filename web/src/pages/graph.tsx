import { t, useI18n } from "../lib/i18n";
import { lazy, Suspense, useMemo, useState } from "react";
import {
  Crosshair,
  Expand,
  Focus,
  Network,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { GraphData, Memory, Project } from "../lib/types";
import { useDebounced, useResource } from "../lib/hooks";
import { excerpt, typeName } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge, Empty, ErrorNotice, Loading } from "../components/common";
import type { Selection } from "../components/memory-detail";
const Scene = lazy(() => import("../components/graph-scene"));
export function GraphPage({
  project,
  onSelect,
}: {
  project: Project;
  onSelect: (s: Selection) => void;
}) {
  useI18n();
  const [mode, setMode] = useState<"2d" | "3d">("3d");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [focus, setFocus] = useState("");
  const [selected, setSelected] = useState<Memory | null>(null);
  const [reset, setReset] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [unsupported, setUnsupported] = useState(false);
  const search = useDebounced(query);
  const { value, loading, error, reload } = useResource<GraphData>(
    "/api/graph",
    { project: project.name, query: search, type, focus },
  );
  function select(memory: Memory) {
    setSelected(memory);
  }
  return (
    <>
      <div className="filter-toolbar">
        <div className="relative min-w-48 flex-1">
          <Search className="search-icon" />
          <Input
            className="pl-10"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label={t("Find a graph node")}
            placeholder={t("Find knowledge on the graph…")}
          />
        </div>
        <select
          aria-label={t("Node type")}
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">{t("All types")}</option>
          {Object.keys(project.types).map((t) => (
            <option key={t} value={t}>
              {typeName(t)}
            </option>
          ))}
        </select>
        {focus && (
          <Button
            variant="outline"
            onClick={() => {
              setFocus("");
              setSelected(null);
            }}
          >
            {t("Entire project")}
          </Button>
        )}
        <div className="segmented">
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={mode === "2d"}
            onClick={() => setMode("2d")}
          >
            2D
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={mode === "3d"}
            disabled={unsupported}
            onClick={() => setMode("3d")}
          >
            3D
          </Button>
        </div>
      </div>
      {unsupported && (
        <p role="status" className="mb-4 text-sm text-muted-foreground">
          {t("WebGL is unavailable. Showing a 2D map with all connections.")}
        </p>
      )}
      {error ? (
        <ErrorNotice error={error} retry={reload} />
      ) : loading ? (
        <Loading label={t("Gathering connections…")} />
      ) : value?.nodes.length ? (
        <>
          <div className="graph-workspace">
            <div className="graph-canvas">
              <div className="graph-caption">
                <Network size={16} />
                <span>
                  {t("{nodes} nodes · {edges} connections", {
                    nodes: value.nodes.length,
                    edges: value.edges.filter((e) => !e.external).length,
                  })}
                </span>
              </div>
              {mode === "3d" ? (
                <Suspense fallback={<Loading label={t("Loading 3D…")} />}>
                  <Scene
                    data={value}
                    selectedId={selected?.id}
                    onSelect={select}
                    reset={reset}
                    onUnsupported={() => {
                      setUnsupported(true);
                      setMode("2d");
                    }}
                  />
                </Suspense>
              ) : (
                <Graph2D
                  data={value}
                  selectedId={selected?.id}
                  onSelect={select}
                  zoom={zoom}
                />
              )}
              <div className="graph-controls">
                {mode === "2d" && (
                  <>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={t("Zoom in on graph")}
                      onClick={() => setZoom(Math.min(3, zoom + 0.25))}
                    >
                      <ZoomIn />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={t("Zoom out of graph")}
                      onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}
                    >
                      <ZoomOut />
                    </Button>
                  </>
                )}
                <Button
                  variant="outline"
                  size="icon"
                  aria-label={t("Reset camera")}
                  onClick={() => {
                    setReset((v) => v + 1);
                    setZoom(1);
                  }}
                >
                  <Expand />
                </Button>
              </div>
              <p className="graph-help">
                {mode === "3d"
                  ? t("Drag to rotate · scroll to zoom")
                  : t("Select a node to see its record")}
              </p>
            </div>
            <aside className="graph-inspector">
              {selected ? (
                <>
                  <Badge>{typeName(selected.type)}</Badge>
                  <h3 className="mt-4">{t("Selected record")}</h3>
                  <p className="mt-3 text-sm leading-7">
                    {excerpt(selected.content, 450)}
                  </p>
                  <Button
                    className="mt-5 w-full"
                    onClick={() =>
                      onSelect({ id: selected.id, project: selected.project })
                    }
                  >
                    {t("Open record")}
                  </Button>
                  <Button
                    variant="outline"
                    className="mt-2 w-full"
                    onClick={() => setFocus(selected.id)}
                  >
                    <Focus />
                    {t("Show neighbors")}
                  </Button>
                </>
              ) : (
                <div className="text-sm leading-7 text-muted-foreground">
                  <Crosshair className="mb-4 text-primary" size={25} />
                  <h3 className="mb-2 text-foreground">
                    {t("Explore connections")}
                  </h3>
                  {t(
                    "Select a node on the map or a record from the list below.",
                  )}
                </div>
              )}
              {focus && (
                <Button
                  className="mt-4 w-full"
                  variant="ghost"
                  onClick={() => {
                    setFocus("");
                    setSelected(null);
                  }}
                >
                  {t("Entire project")}
                </Button>
              )}
              <div className="mt-7 border-t border-border pt-5">
                <p className="text-xs font-semibold text-muted-foreground">
                  {t("Connection types")}
                </p>
                <div className="mt-3 space-y-2 text-xs">
                  <p>
                    <span className="legend-line" />
                    {t("Solves · SOLVES")}
                  </p>
                  <p>
                    <span className="legend-line supersedes" />
                    {t("Supersedes · SUPERSEDES")}
                  </p>
                  <p>
                    <span className="legend-line contradicts" />
                    {t("Contradicts · CONTRADICTS")}
                  </p>
                </div>
              </div>
            </aside>
          </div>
          {value.truncated && (
            <p role="status" className="mt-3 text-sm text-muted-foreground">
              {t(
                "Showing {count} of {total} nodes. Refine your search or explore a selected node’s neighbors.",
                { count: value.nodes.length, total: value.total },
              )}
            </p>
          )}
          {value.edges.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              {t("These records do not have saved connections yet.")}
            </p>
          )}
          <details className="mt-6">
            <summary className="cursor-pointer font-semibold">
              {t("Graph records — accessible list ({count})", {
                count: value.nodes.length,
              })}
            </summary>
            <div className="graph-node-list">
              {value.nodes.map((node) => (
                <button
                  key={node.id}
                  onClick={() => {
                    select(node);
                    onSelect({ id: node.id, project: node.project });
                  }}
                >
                  <Badge>{typeName(node.type)}</Badge>
                  <span>{excerpt(node.content, 110)}</span>
                </button>
              ))}
            </div>
          </details>
        </>
      ) : (
        <Empty title={t("No nodes found")}>
          {t("Change filters or add knowledge to this project.")}
        </Empty>
      )}
    </>
  );
}
function Graph2D({
  data,
  selectedId,
  onSelect,
  zoom,
}: {
  data: GraphData;
  selectedId?: string;
  onSelect: (node: Memory) => void;
  zoom: number;
}) {
  useI18n();
  const positions = useMemo(
    () =>
      new Map(
        data.nodes.map((node, i) => {
          const angle = i * 2.399963;
          const radius =
            24 + Math.sqrt(i / Math.max(1, data.nodes.length)) * 210;
          return [
            node.id,
            {
              x: 400 + Math.cos(angle) * radius * 1.4,
              y: 290 + Math.sin(angle) * radius,
            },
          ];
        }),
      ),
    [data.nodes],
  );
  return (
    <svg
      className="graph-svg"
      viewBox="0 0 800 580"
      role="img"
      aria-label={t(
        "2D knowledge graph; records are also available in the list below",
      )}
    >
      <g transform={`translate(400 290) scale(${zoom}) translate(-400 -290)`}>
        {data.edges.map((edge, i) => {
          const a = positions.get(edge.from_id),
            b = positions.get(edge.to_id);
          return a && b ? (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className={`graph-edge edge-${edge.rel_type.toLowerCase()}`}
            />
          ) : null;
        })}
        {data.nodes.map((node) => {
          const p = positions.get(node.id)!;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-label={excerpt(node.content, 80)}
              onClick={() => onSelect(node)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(node);
                }
              }}
              className="graph-node"
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={selectedId === node.id ? 11 : 6}
                fill={
                  selectedId === node.id
                    ? "var(--graph-selected)"
                    : "var(--graph-node)"
                }
              />
              {(data.nodes.length < 25 || selectedId === node.id) && (
                <text x={p.x + 12} y={p.y + 4}>
                  {excerpt(node.content, 24)}
                </text>
              )}
              <title>{node.content}</title>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
