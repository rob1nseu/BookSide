/** Normalize model LaTeX delimiters before Markdown consumes their backslashes.
 * Code spans/fences and escaped backslashes are deliberately left untouched.
 */
export function normalizeMath(input: string): string {
  const protectedParts = input.split(
    /(`{3,}[^\n]*\n[\s\S]*?`{3,}|~{3,}[^\n]*\n[\s\S]*?~{3,}|`+[^`\n]*`+)/g,
  );
  return protectedParts
    .map((part, index) => {
      if (index % 2) return part;
      const normalized = part.replace(
        /(?<!\\)\\\[([\s\S]*?)(?<!\\)\\\]|(?<!\\)\\\(([^\n]*?)(?<!\\)\\\)/g,
        (_match, block: string | undefined, inline: string | undefined) =>
          block !== undefined
            ? `\n\n$$\n${block.trim()}\n$$\n\n`
            : `$${inline}$`,
      );
      // GFM parses table boundaries before inline math. Encode pipes inside
      // math as equivalent TeX commands so absolute values remain one cell.
      return normalized.replace(/\$\$[\s\S]*?\$\$|(?<!\\)\$[^\n$]+?(?<!\\)\$/g,
        (formula) => formula.replace(/\\\|/g, "\\Vert ").replace(/\|/g, "\\vert "));
    })
    .join("");
}
