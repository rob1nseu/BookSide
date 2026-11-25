import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Prose, Brand } from "./components";
describe("safe readable content", () => {
  it("renders semantic headings and does not execute model HTML", async () => {
    render(
      <Prose>
        {"# 学习目标\n\n<script>alert(1)</script>\n\n理解 **定义**。"}
      </Prose>,
    );
    expect(
      await screen.findByRole("heading", { name: "学习目标" }),
    ).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("定义")).toBeInTheDocument();
  });
  it("renders a readable product identity", () => {
    render(<Brand />);
    expect(screen.getByText("LearNest")).toBeInTheDocument();
    expect(screen.getByText("极简学习")).toBeInTheDocument();
  });
});
