import {
  act,
  fireEvent,
  render,
  screen,
  cleanup,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { useRelease, type ReleaseInfo } from "../lib/releases";
import { request } from "../lib/api";
import { GitHubButton, UpdateDialog, VersionBadge } from "./release-controls";
vi.mock("../lib/api", () => ({ request: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
const baseline: ReleaseInfo = {
  current: "1.0.0",
  running: "1.0.0",
  latest: "1.1.0",
  available: true,
  stars: 6548,
  repository: "https://github.com/VonderVuflya/Yggdrasil",
  releases: "https://github.com/VonderVuflya/Yggdrasil/releases",
  checking: false,
  check_error: false,
  restart_required: false,
  update: null,
};
function Harness() {
  const release = useRelease();
  return (
    <>
      <VersionBadge release={release} />
      <GitHubButton release={release} />
      <UpdateDialog release={release} />
    </>
  );
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
  sessionStorage.clear();
});
it("links the current version to releases when no update is available, and uses real star counts", async () => {
  vi.mocked(request).mockResolvedValue({ ...baseline, available: false });
  await act(async () => {
    render(<Harness />);
  });
  expect(
    screen.getByRole("link", { name: /v1.0.0.*Release notes/ }),
  ).toHaveAttribute("href", baseline.releases);
  expect(
    screen.getByRole("link", { name: "GitHub project · 6,548 stars" }),
  ).toHaveAttribute("href", baseline.repository);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("links releases after an external CLI upgrade instead of offering a dead restart dialog", async () => {
  vi.mocked(request).mockResolvedValue({
    ...baseline,
    current: "1.1.0",
    available: false,
    restart_required: true,
    update: null,
  });
  await act(async () => {
    render(<Harness />);
  });
  expect(
    screen.getByRole("link", { name: /v1.1.0.*Release notes/ }),
  ).toHaveAttribute("href", baseline.releases);
  expect(
    screen.queryByRole("button", { name: /Restart Workspace/ }),
  ).not.toBeInTheDocument();
});
it("never fabricates stars when GitHub is unreachable", async () => {
  vi.mocked(request).mockResolvedValue({ ...baseline, stars: null });
  await act(async () => {
    render(<Harness />);
  });
  expect(
    screen.getByRole("link", { name: "GitHub project" }),
  ).toHaveTextContent("—");
});
it("keeps updating after hiding the dialog, resumes the log, and toasts success once", async () => {
  vi.useFakeTimers();
  let data = { ...baseline };
  vi.mocked(request).mockImplementation(async (path, body) => {
    if (path === "/api/release/update") {
      expect(body).toEqual({ confirmed: true });
      data = {
        ...baseline,
        update: {
          id: "one",
          target: "1.1.0",
          previous: "1.0.0",
          status: "running",
          output: "Downloading package…",
          exit_code: null,
        },
      };
    }
    return data;
  });
  await act(async () => {
    render(<Harness />);
  });
  fireEvent.click(screen.getByRole("button", { name: /Update available/ }));
  expect(screen.getByRole("dialog")).toHaveTextContent(
    "Install the latest version?",
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Update now" }));
  });
  expect(screen.getByLabelText("Update output")).toHaveTextContent(
    "Downloading package…",
  );
  fireEvent.click(screen.getByRole("button", { name: "Hide" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    screen
      .getByRole("button", { name: /Updating Yggdrasil/ })
      .querySelector(".animate-spin"),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Updating Yggdrasil/ }));
  expect(screen.getByLabelText("Update output")).toHaveTextContent(
    "Downloading package…",
  );
  data = {
    ...data,
    current: "1.1.0",
    running: "1.1.0",
    available: false,
    update: { ...data.update!, status: "completed", exit_code: 0 },
  };
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1500);
  });
  expect(toast.success).toHaveBeenCalledWith("Yggdrasil updated to 1.1.0");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(toast.success).toHaveBeenCalledTimes(1);
});
it("shows a failed update without reporting success", async () => {
  vi.mocked(request).mockResolvedValue({
    ...baseline,
    update: {
      id: "failed",
      target: "1.1.0",
      previous: "1.0.0",
      status: "failed",
      output: "Installer failed",
      exit_code: 1,
      error: "The update did not complete. Review the output and try again.",
    },
  });
  await act(async () => {
    render(<Harness />);
  });
  fireEvent.click(screen.getByRole("button", { name: /Update available/ }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "The update did not complete",
  );
  expect(
    screen.getByRole("button", { name: "Retry update" }),
  ).toBeInTheDocument();
  expect(toast.success).not.toHaveBeenCalled();
});
it("requests Workspace restart only after the backend verifies the installed update", async () => {
  vi.useFakeTimers();
  vi.mocked(request).mockImplementation(async (path) =>
    path === "/api/release/restart"
      ? { ok: true }
      : {
          ...baseline,
          current: "1.1.0",
          restart_required: true,
          available: false,
          update: {
            id: "restart",
            target: "1.1.0",
            previous: "1.0.0",
            status: "completed",
            output: "Done",
            exit_code: 0,
          },
        },
  );
  await act(async () => {
    render(<Harness />);
  });
  expect(request).toHaveBeenCalledWith(
    "/api/release/restart",
    {},
    undefined,
    expect.any(AbortSignal),
  );
  expect(
    screen.getByRole("button", { name: /Updating Yggdrasil/ }),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1500);
  });
  expect(
    vi
      .mocked(request)
      .mock.calls.filter(([path]) => path === "/api/release/restart"),
  ).toHaveLength(1);
  expect(toast.success).not.toHaveBeenCalled();
});
it("offers retry when an active operation prevents Workspace restart", async () => {
  vi.useFakeTimers();
  vi.mocked(request).mockImplementation(async (path) => {
    if (path === "/api/release/restart")
      throw new Error(
        "Another CLI job is running; wait for it or stop it first.",
      );
    return {
      ...baseline,
      current: "1.1.0",
      restart_required: true,
      available: false,
      update: {
        id: "busy",
        target: "1.1.0",
        previous: "1.0.0",
        status: "completed",
        output: "Done",
        exit_code: 0,
      },
    };
  });
  await act(async () => {
    render(<Harness />);
  });
  fireEvent.click(
    screen.getByRole("button", { name: /v1.1.0.*Restart Workspace/ }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Another CLI job is running",
  );
  expect(
    screen.getByRole("button", { name: "Restart Workspace" }),
  ).toBeInTheDocument();
  expect(toast.success).not.toHaveBeenCalled();
});
