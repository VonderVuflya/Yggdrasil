import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, it, expect } from "vitest";
import { ModelSelect } from "./model-select";

it("offers only discovered installed models and keeps unavailable saved model labelled", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          reachable: true,
          models: [{ id: "installed-chat", kind: "llm" }],
        }),
      ),
    ),
  );
  const change = vi.fn();
  render(
    <ModelSelect
      id="model"
      provider="ollama"
      url="http://localhost:11434"
      purpose="chat"
      value="old-model"
      onChange={change}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("option", { name: "installed-chat" }),
    ).toBeInTheDocument(),
  );
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: /old-model/ })).toBeDisabled();
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "installed-chat" },
  });
  expect(change).toHaveBeenCalledWith("installed-chat");
});

it("distinguishes an unreachable runtime from an empty catalog", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          reachable: false,
          models: [],
          error: "Model server is unavailable.",
        }),
      ),
    ),
  );
  render(
    <ModelSelect
      id="model"
      provider="ollama"
      url="http://localhost:11434"
      purpose="chat"
      value=""
      onChange={() => {}}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByText("Model server is unavailable."),
    ).toBeInTheDocument(),
  );
});
