export type Scope = string | null;
export interface Memory {
  id: string;
  content: string;
  project: string;
  type: string;
  source: string;
  created_at: number;
  archived: boolean;
  metadata: Record<string, unknown>;
}
export interface Project {
  name: string;
  count: number;
  archived_count: number;
  latest_at: number;
  types: Record<string, number>;
}
export interface Edge {
  from_id: string;
  to_id: string;
  rel_type: string;
  external?: boolean;
  other_project?: string;
}
export interface GraphData {
  nodes: Memory[];
  edges: Edge[];
  total: number;
  truncated: boolean;
}
export interface Chat {
  id: string;
  project: Scope;
  title: string;
  created_at: number;
  updated_at: number;
  memory_id?: string;
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "stopped" | "error" | "search_only";
  sources: Memory[];
  created_at: number;
  truncated?: boolean;
}
export interface Settings {
  configured: boolean;
  provider: "ollama" | "openai";
  url: string;
  model: string;
  has_key: boolean;
  suggested_url: string;
  suggested_model: string;
}
export type StreamEvent =
  | { type: "sources"; sources: Memory[]; truncated: boolean }
  | { type: "delta"; text: string }
  | { type: "done"; message: Message }
  | { type: "error"; error: string; message?: Message };
