import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Prose, Brand } from "./components";
import { normalizeMath } from "./math";
import AnswerEditor from "./AnswerEditor";
describe("safe readable content", () => {
  it("keeps absolute values inside math table cells", async () => {
    const { container } = render(<Prose>{String.raw`| 函数 | 定义域 |
| --- | --- |
| $x^2,\cos x,|x|$ | $\mathbb{R}$ |`}</Prose>);
    await waitFor(() => expect(container.querySelectorAll(".katex")).toHaveLength(2), {timeout: 5000});
    expect(container.querySelectorAll("tbody td")).toHaveLength(2);
    expect(container.querySelector(".katex-error")).toBeNull();
  });
  it("renders formulas in selectable answer options", async () => {
    const { container } = render(<AnswerEditor question={{id:"formula-option",position:0,kind:"choice",prompt:"选择",options:[String.raw`$A\setminus B=A\cap B^{c}$`],unit:""}} spaceId="math-test" disabled={false} onSubmit={async () => true} />);
    await waitFor(() => expect(container.querySelector("label .katex")).not.toBeNull());
    expect(screen.getByRole("radio")).toBeInTheDocument();
  });
  it("renders semantic headings and does not execute model HTML", async () => {
    render(
      <Prose>
        {"# 学习目标\n\n<script>alert(1)</script>\n\n理解 **定义**。"}
      </Prose>,
    );
    expect(
      await screen.findByRole(
        "heading",
        { name: "学习目标" },
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("定义")).toBeInTheDocument();
  });
  it("renders a readable product identity", () => {
    render(<Brand />);
    expect(screen.getByText("LearNest")).toBeInTheDocument();
    expect(screen.getByText("极简学习")).toBeInTheDocument();
  });
  it("renders all four math delimiters, matrices and aligned equations", async () => {
    const { container } = render(
      <Prose>{String.raw`行内 $x^2$ 和 \(\frac{1}{2}\)。

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

\[\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}\]

\[\begin{aligned}a &= b+c \\ d &= e\end{aligned}\]`}</Prose>,
    );
    await screen.findByText("行内", { exact: false });
    expect(container.querySelectorAll(".katex")).toHaveLength(5);
    expect(container.querySelectorAll(".katex-display")).toHaveLength(3);
    expect(container.querySelector(".katex-error")).toBeNull();
  });
  it("preserves code and escaped delimiters and exposes malformed math without crashing", async () => {
    const code = String.raw`\(x\)`;
    const fenced = "```tex\n" + code + "\n```";
    expect(normalizeMath("`" + code + "`\n" + fenced)).toBe(
      "`" + code + "`\n" + fenced,
    );
    expect(normalizeMath(String.raw`\\(literal\\)`)).toBe(
      String.raw`\\(literal\\)`,
    );
    const { container } = render(<Prose>{String.raw`$\frac{1}{$`}</Prose>);
    await waitFor(() =>
      expect(container.querySelector(".katex-error")).not.toBeNull(),
    );
  });
});
