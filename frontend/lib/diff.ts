export type DiffKind = "add" | "remove" | "context" | "meta";

export type DiffLine = {
  kind: DiffKind;
  text: string;
};

export type ParsedDiff = {
  added: number;
  removed: number;
  lines: DiffLine[];
};

function classify(text: string): DiffLine {
  if (
    text.startsWith("diff --git ") ||
    text.startsWith("index ") ||
    text.startsWith("--- ") ||
    text.startsWith("+++ ") ||
    text.startsWith("@@")
  ) {
    return { kind: "meta", text };
  }
  if (text.startsWith("+")) return { kind: "add", text };
  if (text.startsWith("-")) return { kind: "remove", text };
  return { kind: "context", text };
}

export function parseDiff(source: string): ParsedDiff | null {
  const normalized = source.replace(/\r\n/g, "\n").replace(/\n$/, "");
  if (normalized.trim() === "") return null;

  const lines = normalized.split("\n").map(classify);
  const parsed = lines.some(
    (line) => line.kind === "add" || line.kind === "remove" || line.kind === "meta",
  );
  if (!parsed) return null;

  let added = 0;
  let removed = 0;
  for (const line of lines) {
    if (line.kind === "add") added += 1;
    if (line.kind === "remove") removed += 1;
  }
  return { added, removed, lines };
}
