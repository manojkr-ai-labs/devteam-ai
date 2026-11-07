import React from "react";

import { parseDiff, type DiffKind } from "@/lib/diff";

export type PatchModel = {
  summary: string;
  affectedFiles: string[];
  diff: string;
};

const TEXT: Record<DiffKind, string> = {
  add: "text-ink",
  remove: "text-brick",
  context: "text-ink",
  meta: "text-graphite",
};

export function DiffView({ patch }: { patch: PatchModel | null }) {
  if (!patch) return null;
  const parsed = parseDiff(patch.diff);

  return (
    <section id="patch" className="mt-12" aria-labelledby="patch-title">
      <div className="border-b border-hairline pb-3">
        <h2 id="patch-title" className="font-sans text-section font-semibold text-graphite">
          03 / PATCH
        </h2>
      </div>
      <p className="mt-6 max-w-[40rem] font-sans text-prose text-ink">{patch.summary}</p>
      {patch.affectedFiles.length > 0 ? (
        <ul className="mt-4">
          {patch.affectedFiles.map((file) => (
            <li
              key={file}
              className="border-b border-hairline py-2 font-courier text-meta text-ink"
            >
              {file}
            </li>
          ))}
        </ul>
      ) : null}
      {parsed ? (
        <div className="mt-6 max-h-96 overflow-auto border border-hairline bg-surface">
          <div className="flex items-baseline justify-between gap-6 border-b border-hairline px-4 py-3">
            <p className="min-w-0 truncate font-courier text-[12px] leading-5 text-ink">
              {patch.affectedFiles.join(", ")}
            </p>
            <p className="shrink-0 font-sans text-section font-semibold text-graphite">
              {`+${parsed.added} / \u2212${parsed.removed}`}
            </p>
          </div>
          <div className="min-w-max py-2">
            {parsed.lines.map((line, index) => (
              <div key={index} data-line={line.kind} className="flex">
                <span
                  aria-hidden="true"
                  className={`w-[2px] shrink-0 ${
                    line.kind === "add" ? "bg-pine" : "bg-transparent"
                  }`}
                />
                <span
                  className={`whitespace-pre pl-3 font-courier text-[12px] leading-5 ${TEXT[line.kind]}`}
                >
                  {line.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
