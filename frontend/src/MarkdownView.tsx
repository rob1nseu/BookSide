import Markdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import { memo, useMemo } from "react";
import { normalizeMath } from "./math";
const remarkPlugins = [remarkMath, remarkGfm];
const rehypePlugins = [rehypeKatex];
export default memo(function MarkdownView({ children }: { children: string }) {
  const content = useMemo(() => normalizeMath(children), [children]);
  return (
    <div className="prose">
      <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>
        {content}
      </Markdown>
    </div>
  );
});
