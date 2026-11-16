import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChatPage } from "./chat";
it("does not display messages from a chat belonging to another project", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    return new Response(
      JSON.stringify(
        path.endsWith("/list")
          ? { chats: [] }
          : {
              chat: {
                id: "foreign",
                project: "Beta",
                title: "Чужой",
                created_at: 1,
                updated_at: 1,
              },
              messages: [
                {
                  id: "m",
                  role: "assistant",
                  content: "Секрет Beta",
                  status: "complete",
                  sources: [],
                  created_at: 1,
                },
              ],
            },
      ),
    );
  });
  render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="foreign" onSelect={() => {}} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This conversation belongs to another project",
  );
  expect(screen.queryByText("Секрет Beta")).not.toBeInTheDocument();
});
it("ignores a late streaming response after navigation to another conversation", async () => {
  const user = (await import("@testing-library/user-event")).default;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
    },
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/messages")) return new Response(stream);
    if (path.endsWith("/stop")) return new Response("{}");
    if (path.endsWith("/list")) return new Response('{"chats":[]}');
    const id = path.endsWith("/new") ? "new" : "old";
    return new Response(
      JSON.stringify({
        chat: { id, project: "Alpha", title: id, created_at: 1, updated_at: 1 },
        messages:
          id === "new"
            ? [
                {
                  id: "new-message",
                  role: "user",
                  content: "Новый разговор",
                  status: "complete",
                  sources: [],
                  created_at: 1,
                },
              ]
            : [],
      }),
    );
  });
  const view = render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="old" onSelect={() => {}} />
    </MemoryRouter>,
  );
  const input = await screen.findByRole("textbox", { name: "Your question" });
  await vi.waitFor(() => expect(input).not.toBeDisabled());
  await user.type(input, "Старый вопрос");
  await user.click(screen.getByRole("button", { name: "Send question" }));
  view.rerender(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="new" onSelect={() => {}} />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Новый разговор")).toBeInTheDocument();
  streamController!.enqueue(
    new TextEncoder().encode(
      '{"type":"delta","text":"Поздний старый ответ"}\n',
    ),
  );
  streamController!.close();
  await vi.waitFor(() =>
    expect(screen.queryByText("Поздний старый ответ")).not.toBeInTheDocument(),
  );
  expect(screen.getByText("Новый разговор")).toBeInTheDocument();
});
it("clears the previous history when opening a new conversation", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/list")
            ? { chats: [] }
            : {
                chat: {
                  id: "old",
                  project: "Alpha",
                  title: "Old",
                  created_at: 1,
                  updated_at: 1,
                },
                messages: [
                  {
                    id: "m",
                    role: "user",
                    content: "Старый разговор",
                    status: "complete",
                    sources: [],
                    created_at: 1,
                  },
                ],
              },
        ),
      ),
  );
  const view = render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="old" onSelect={() => {}} />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Старый разговор")).toBeInTheDocument();
  view.rerender(
    <MemoryRouter>
      <ChatPage project="Alpha" onSelect={() => {}} />
    </MemoryRouter>,
  );
  expect(screen.queryByText("Старый разговор")).not.toBeInTheDocument();
  expect(
    screen.getByRole("textbox", { name: "Your question" }),
  ).not.toBeDisabled();
});
it("rejects the Enter shortcut when the loaded conversation scope is wrong", async () => {
  const { fireEvent } = await import("@testing-library/react");
  const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/list")
            ? { chats: [] }
            : {
                chat: {
                  id: "foreign",
                  project: "Beta",
                  title: "Foreign",
                  created_at: 1,
                  updated_at: 1,
                },
                messages: [],
              },
        ),
      ),
  );
  render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="foreign" onSelect={() => {}} />
    </MemoryRouter>,
  );
  await screen.findByRole("alert");
  const input = screen.getByRole("textbox", { name: "Your question" });
  fireEvent.change(input, { target: { value: "Чужой вопрос" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(input).toBeDisabled();
  expect(
    fetcher.mock.calls.some(([url]) => String(url).endsWith("/messages")),
  ).toBe(false);
});
it("unblocks a new conversation when navigation interrupts slow chat creation", async () => {
  const user = (await import("@testing-library/user-event")).default;
  let resolveCreate!: (value: Response) => void;
  const create = new Promise<Response>((resolve) => {
    resolveCreate = resolve;
  });
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      if (String(input) === "/api/chats") return create;
      if (String(input).endsWith("/list")) return new Response('{"chats":[]}');
      return new Response(
        JSON.stringify({
          chat: {
            id: "other",
            project: "Alpha",
            title: "Other",
            created_at: 1,
            updated_at: 1,
          },
          messages: [
            {
              id: "other-message",
              role: "user",
              content: "Другой разговор",
              status: "complete",
              sources: [],
              created_at: 1,
            },
          ],
        }),
      );
    });
  const view = render(
    <MemoryRouter>
      <ChatPage project="Alpha" onSelect={() => {}} />
    </MemoryRouter>,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Your question" }),
    "Медленный вопрос",
  );
  await user.click(screen.getByRole("button", { name: "Send question" }));
  view.rerender(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="other" onSelect={() => {}} />
    </MemoryRouter>,
  );
  await screen.findByText("Другой разговор");
  expect(
    screen.getByRole("textbox", { name: "Your question" }),
  ).not.toBeDisabled();
  resolveCreate(
    new Response(
      JSON.stringify({
        id: "late",
        project: "Alpha",
        title: "Late",
        created_at: 1,
        updated_at: 1,
      }),
    ),
  );
  await vi.waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: "Your question" }),
    ).not.toBeDisabled(),
  );
  expect(
    fetcher.mock.calls.some(([url]) => String(url).endsWith("/messages")),
  ).toBe(false);
});
it("shows sources only for the selected response and opens citations from their own response", async () => {
  const user = (await import("@testing-library/user-event")).default;
  const { within } = await import("@testing-library/react");
  const onSelect = vi.fn();
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/list")
            ? { chats: [] }
            : {
                chat: {
                  id: "chat",
                  project: "Alpha",
                  title: "Chat",
                  created_at: 1,
                  updated_at: 1,
                },
                messages: [
                  {
                    id: "first",
                    role: "assistant",
                    content: "First answer [1]",
                    status: "complete",
                    created_at: 1,
                    sources: [
                      { id: "one", project: "Alpha", content: "First source" },
                    ],
                  },
                  {
                    id: "second",
                    role: "assistant",
                    content: "Second answer [1]",
                    status: "complete",
                    created_at: 2,
                    sources: [
                      { id: "two", project: "Beta", content: "Second source" },
                    ],
                  },
                ],
              },
        ),
      ),
  );
  render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="chat" onSelect={onSelect} />
    </MemoryRouter>,
  );
  await screen.findByText("Second source");
  const panel = screen.getByRole("complementary", { name: "Response sources" });
  expect(within(panel).getByText("Second source")).toBeInTheDocument();
  expect(screen.queryByText("First source")).not.toBeInTheDocument();
  const buttons = screen.getAllByRole("button", { name: "Sources (1)" });
  await user.click(buttons[0]);
  expect(buttons[0]).toHaveAttribute("aria-pressed", "true");
  expect(within(panel).getByText("First source")).toBeInTheDocument();
  expect(screen.queryByText("Second source")).not.toBeInTheDocument();
  expect(
    within(panel).getByRole("button", { name: "Response sources 1" }),
  ).toHaveAttribute("aria-expanded", "true");
  await user.click(screen.getByRole("button", { name: "Source 1: Beta" }));
  expect(onSelect).toHaveBeenLastCalledWith({ id: "two", project: "Beta" });
  await user.click(within(panel).getByRole("button", { name: /First source/ }));
  expect(onSelect).toHaveBeenLastCalledWith({ id: "one", project: "Alpha" });
  await user.click(
    within(panel).getByRole("button", { name: "Response sources 1" }),
  );
  expect(
    within(panel).getByRole("button", { name: "Response sources 1" }),
  ).toHaveAttribute("aria-expanded", "false");
});
it("localizes built-in search-only responses without translating actual answers", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/list")
            ? { chats: [] }
            : {
                chat: { id: "chat", project: "Alpha" },
                messages: [
                  {
                    id: "m",
                    role: "assistant",
                    content: "В памяти не найдено данных для ответа.",
                    status: "search_only",
                    sources: [],
                    created_at: 1,
                  },
                ],
              },
        ),
      ),
  );
  render(
    <MemoryRouter>
      <ChatPage project="Alpha" chatId="chat" onSelect={vi.fn()} />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText(
      "No matching memory was found. Refine your question or add knowledge to this project.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("В памяти не найдено данных для ответа."),
  ).not.toBeInTheDocument();
});
