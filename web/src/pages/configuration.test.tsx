import { render, screen, fireEvent } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import { ConfigurationPanel } from "./configuration";
it("shows effective defaults and writes only edited settings through shared config API", async () => {
  const values = {
    groups: [
      {
        id: "test",
        label: "Configuration",
        settings: [
          {
            key: "distill_timeout",
            value: "120",
            stored_value: null,
            source: "default",
            default: "120",
            description: "Timeout",
            secret: false,
            has_value: true,
            restart_required: false,
            type: "number",
          },
          {
            key: "distill_api_key",
            value: "",
            stored_value: "",
            source: "keyfile",
            default: "",
            description: "Key",
            secret: true,
            has_value: true,
            restart_required: false,
            type: "string",
          },
        ],
      },
    ],
    identity: { user_id: "local", namespace: "personal" },
  };
  let written: unknown;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_path: unknown, init?: RequestInit) => {
      if (init?.method === "PUT") {
        written = JSON.parse(String(init.body));
      }
      return new Response(JSON.stringify(values));
    }),
  );
  render(<ConfigurationPanel />);
  const field = await screen.findByLabelText("distill_timeout");
  expect(field).toHaveValue(120);
  expect(screen.getByLabelText("distill_api_key")).toHaveValue("");
  fireEvent.change(field, { target: { value: "180" } });
  fireEvent.click(screen.getByRole("button", { name: "Save configuration" }));
  await screen.findByText("Configuration saved.");
  expect(written).toEqual({ values: { distill_timeout: "180" }, unset: [] });
});

it("discovers models against prospective reset defaults without a key pending removal", async () => {
  const make = (key: string, value: string, def: string, extra = {}) => ({
    key,
    value,
    stored_value: value,
    source: "config",
    default: def,
    description: key,
    secret: false,
    has_value: true,
    restart_required: true,
    type: "string",
    ...extra,
  });
  const settings = [
    make("embed_backend", "openai", "ollama", {
      type: "select",
      options: ["openai", "ollama"],
    }),
    make("embed_url", "http://localhost:1234/v1", "http://127.0.0.1:11434"),
    make("embed_api_key", "", "", { secret: true, source: "keyfile" }),
    make("embed_model", "old-model", ""),
  ];
  const probes: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: unknown, init?: RequestInit) => {
      if (path === "/api/models") {
        probes.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify({ reachable: true, models: [] }));
      }
      return new Response(
        JSON.stringify({
          groups: [{ id: "models", label: "Models", settings }],
          identity: { user_id: "local", namespace: "personal" },
        }),
      );
    }),
  );
  render(<ConfigurationPanel />);
  const { within, waitFor } = await import("@testing-library/react");
  await screen.findByLabelText("embed_url");
  for (const key of ["embed_url", "embed_backend", "embed_api_key"]) {
    const row = screen
      .getByLabelText(key)
      .closest(".config-field") as HTMLElement;
    fireEvent.click(
      within(row).getByRole("button", { name: "Reset to default" }),
    );
  }
  await waitFor(() =>
    expect(probes.at(-1)).toMatchObject({
      purpose: "embed",
      provider: "ollama",
      url: "http://127.0.0.1:11434",
      api_key: "",
    }),
  );
});
