import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ReviewPanel from "./ReviewPanel";
import { api } from "./api";

vi.mock("./api", () => ({ api: vi.fn() }));
vi.mock("./MindMap", () => ({ default: () => <div>已恢复的章节导图</div> }));

it("restores a completed map when reconnecting to a run started before page reload", async () => {
  const empty = {
    title: "函数",
    map: null,
    session: null,
    states: {},
    round_states: {},
  };
  vi.mocked(api)
    .mockResolvedValueOnce(empty)
    .mockResolvedValueOnce({ ...empty, map: { title: "函数", nodes: [] } });
  const props = {
    spaceId: "s",
    chapterId: "c",
    act: vi.fn(),
    result: null,
    onError: vi.fn(),
    cite: vi.fn(),
  };
  const { rerender } = render(<ReviewPanel {...props} active={false} />);
  await screen.findByRole("button", { name: "生成章节思维导图" });
  // The inherited run has no local button promise waiting to refresh this panel.
  rerender(<ReviewPanel {...props} active={true} />);
  rerender(<ReviewPanel {...props} active={false} />);
  await screen.findByText("已恢复的章节导图");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "本章练一轮" })).toBeEnabled(),
  );
  expect(props.act).not.toHaveBeenCalled();
});
