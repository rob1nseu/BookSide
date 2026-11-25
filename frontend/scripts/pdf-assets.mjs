import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
function copyDirectory(source, target) {
  mkdirSync(target, { recursive: true });
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const from = resolve(source, entry.name),
      to = resolve(target, entry.name);
    if (entry.isDirectory()) copyDirectory(from, to);
    else if (entry.isFile()) copyFileSync(from, to);
  }
}
for (const directory of ["cmaps", "standard_fonts", "wasm"]) {
  const target = resolve("public/pdf", directory);
  mkdirSync(target, { recursive: true });
  copyDirectory(resolve("node_modules/pdfjs-dist", directory), target);
}
