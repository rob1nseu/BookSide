/** Tokenize code and math together so TeX is normalized exactly once.
 * Never globally unescape backslashes: that would destroy matrix row separators.
 */
export function normalizeMath(input: string): string {
  return input.replace(
    /(`{3,}[^\n]*\n[\s\S]*?`{3,}|~{3,}[^\n]*\n[\s\S]*?~{3,}|`+[^`\n]*`+)|(?<!\\)\\\[([\s\S]*?)(?<!\\)\\\]|(?<!\\)\\\(([\s\S]*?)(?<!\\)\\\)|(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$|(?<!\\)\$([^\n$]+?)(?<!\\)\$|(?<!\\)(\\begin\{(align\*?|equation\*?|gather\*?|aligned|gathered|cases|[bpBvV]?matrix)\}[\s\S]*?\\end\{\7\})/g,
    (
      match,
      code,
      bracket,
      inline,
      dollars,
      single,
      environment,
      _name,
      offset: number,
      full: string,
    ) => {
      if (code) return code;
      let tex = String(bracket ?? inline ?? dollars ?? single ?? environment);
      tex = tex
        .replace(/\\(begin|end)\{align\*?\}/g, "\\$1{aligned}")
        .replace(/\\(begin|end)\{(?:equation|gather)\*?\}/g, "\\$1{gathered}")
        .replace(/\\\|/g, "\\Vert ")
        .replace(/\|/g, "\\vert ");
      const display =
        bracket !== undefined ||
        dollars !== undefined ||
        environment !== undefined;
      // A display delimiter inside a table must not split the Markdown row.
      const line = full.slice(full.lastIndexOf("\n", offset - 1) + 1, offset);
      if (!display || /^\s*\|/.test(line))
        return `$${tex.trim().replace(/\n/g, " ")}$`;
      const before = full.slice(0, offset).match(/\n*$/)?.[0].length || 0;
      const after =
        full.slice(offset + match.length).match(/^\n*/)?.[0].length || 0;
      return `${"\n".repeat(Math.max(0, 2 - before))}$$\n${tex.trim()}\n$$${"\n".repeat(Math.max(0, 2 - after))}`;
    },
  );
}
