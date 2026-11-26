import Markdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import { memo, useMemo } from "react";
import { normalizeMath } from "./math";
const remarkPlugins = [remarkMath, remarkGfm];
const rehypePlugins = [rehypeKatex];
export default memo(function MarkdownView({
  children,
  inline = false,
}: {
  children: string;
  inline?: boolean;
}) {
  const content = useMemo(() => normalizeMath(children), [children]);
  const Wrapper = inline ? "span" : "div";
  return (
    <Wrapper className={inline ? "prose prose-inline" : "prose"}>
      <Markdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={{
          p: ({ children }) =>
            inline ? <span>{children}</span> : <p>{children}</p>,
          span: ({ node: _node, className, children, ...props }) =>
            className === "katex-error" ? (
              <span
                className="katex-error math-fallback"
                role="note"
                title={props.title}
              >
                <small>公式未能排版 · 原式：</small>
                <code>{children}</code>
              </span>
            ) : (
              <span {...props} className={className}>
                {children}
              </span>
            ),
        }}
      >
        {content}
      </Markdown>
    </Wrapper>
  );
});
