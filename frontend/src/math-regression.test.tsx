import { render, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import MarkdownView from "./MarkdownView";
import { normalizeMath } from "./math";
afterEach(cleanup);
const cases = [
  String.raw`$$\frac{1}{2}$$`,
  String.raw`\begin{align}a&=b+c\\d&=e\end{align}`,
  String.raw`\begin{equation}E=mc^2\end{equation}`,
  String.raw`\[\begin{cases}x^2&x>0\\0&x\le 0\end{cases}\]`,
  String.raw`$\left|x\right| + \|v\|$`,
  String.raw`$\sum_{i=1}^{n}i=\frac{n(n+1)}2$`,
  String.raw`$\lim_{x\to0}\frac{\sin x}{x}=1$`,
  String.raw`$\mathbb{R}\setminus\{0\}, A\subseteq B$`,
  String.raw`$\nabla f,\frac{\partial f}{\partial x},\boldsymbol{v}$`,
  String.raw`$\underbrace{a+b}_{\text{总和}}$`,
  String.raw`\begin{pmatrix}1&2\\3&4\end{pmatrix}`,
  "\\(a +\nb\\)",
];
it.each(cases)("renders supported math without fallback: %s", async (tex) => {
  const { container } = render(<MarkdownView>{tex}</MarkdownView>);
  await waitFor(() =>
    expect(container.querySelectorAll(".katex")).toHaveLength(1),
  );
  expect(container.querySelector(".katex-error")).toBeNull();
  expect(container.querySelector(".katex-html [style]")).not.toBeNull();
  expect(normalizeMath(normalizeMath(tex))).toBe(normalizeMath(tex));
});
it("protects ordinary code, escaped dollars and matrix row separators", () => {
  const text = '```python\nprint("$x$")\n```\n`\\(x\\)`\n价格 \\$5';
  expect(normalizeMath(text)).toBe(text);
  expect(
    normalizeMath(String.raw`\[\begin{matrix}1\\2\end{matrix}\]`),
  ).toContain(String.raw`1\\2`);
});
it("does not split display math in a table or remove KaTeX positioning", () => {
  const { container } = render(
    <MarkdownView>{"| a | b |\n|---|---|\n| $$x^2$$ | $|x|$ |"}</MarkdownView>,
  );
  expect(container.querySelectorAll("tbody td")).toHaveLength(2);
  expect(container.querySelectorAll(".katex")).toHaveLength(2);
});
