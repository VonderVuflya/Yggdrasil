import { t } from "./i18n";
import type { StreamEvent } from "./types";
const headers = { "Content-Type": "application/json", "X-Ygg-Request": "1" };
export async function checked(response: Response) {
  if (!response.ok) {
    let message = t("Request failed ({status})", { status: response.status });
    try {
      message = (await response.json()).error || message;
    } catch {
      /* preserve status */
    }
    throw new Error(message);
  }
  return response;
}
export async function request<T>(
  path: string,
  body?: unknown,
  method?: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await checked(
    await fetch(path, {
      method: method || (body === undefined ? "GET" : "POST"),
      credentials: "same-origin",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    }),
  );
  return response.json();
}
export async function establishSession() {
  const ticket = new URLSearchParams(window.location.hash.slice(1)).get(
    "ticket",
  );
  if (ticket) {
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    await request("/api/session", { ticket });
  }
}
export async function* readEvents(
  response: Response,
): AsyncGenerator<StreamEvent> {
  await checked(response);
  if (!response.body) throw new Error(t("Response stream unavailable"));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 1);
        if (line) yield JSON.parse(line);
      }
      if (done) {
        if (buffer.trim()) yield JSON.parse(buffer);
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
export async function streamChat(
  id: string,
  content: string,
  signal: AbortSignal,
) {
  return fetch(`/api/chats/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify({ content }),
    signal,
  });
}
