export interface DiffLine {
  kind: "context" | "add" | "remove";
  text: string;
}

/** Dependency-free line diff (Myers-style LCS over lines), good enough for
 * the short file edits agent tool calls produce. Not meant for huge files. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before === "" ? [] : before.split("\n");
  const b = after === "" ? [] : after.split("\n");
  const rows = a.length;
  const cols = b.length;
  const lcs: number[][] = Array.from({ length: rows + 1 }, () => new Array<number>(cols + 1).fill(0));

  for (let i = rows - 1; i >= 0; i--) {
    for (let j = cols - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (a[i] === b[j]) {
      lines.push({ kind: "context", text: a[i] });
      i += 1;
      j += 1;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      lines.push({ kind: "remove", text: a[i] });
      i += 1;
    } else {
      lines.push({ kind: "add", text: b[j] });
      j += 1;
    }
  }
  while (i < rows) {
    lines.push({ kind: "remove", text: a[i] });
    i += 1;
  }
  while (j < cols) {
    lines.push({ kind: "add", text: b[j] });
    j += 1;
  }
  return lines;
}
