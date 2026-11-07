import React from "react";

export type EvidenceItem = {
  id: string;
  path: string;
  startLine: number;
  endLine: number;
  excerpt: string;
  reason: string;
};

export type FindingModel = {
  id: string;
  hypothesis: string;
  uncertainties: string;
  evidence: EvidenceItem[];
};

export function EvidenceList({ findings }: { findings: FindingModel[] }) {
  const rows = findings.flatMap((finding) => finding.evidence);
  if (rows.length === 0) return null;

  const notes = findings
    .map((finding) => finding.uncertainties.trim())
    .filter((note) => note !== "");

  return (
    <section id="evidence" className="mt-12" aria-labelledby="evidence-title">
      <div className="border-b border-hairline pb-3">
        <h2
          id="evidence-title"
          className="font-sans text-section font-semibold text-graphite"
        >
          02 / EVIDENCE
        </h2>
      </div>
      {findings.map((finding) =>
        finding.hypothesis.trim() === "" ? null : (
          <p key={finding.id} className="mt-6 max-w-[40rem] font-sans text-prose text-ink">
            {finding.hypothesis}
          </p>
        ),
      )}
      <table className="mt-6 w-full border border-hairline bg-surface text-left">
        <thead>
          <tr className="border-b border-hairline">
            <th className="px-6 py-3 font-sans text-section font-semibold text-graphite">
              PATH
            </th>
            <th className="px-6 py-3 font-sans text-section font-semibold text-graphite">
              LINES
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-hairline last:border-b-0">
              <td className="px-6 py-3 font-courier text-meta text-ink">{row.path}</td>
              <td className="px-6 py-3 font-courier text-meta text-graphite">
                {row.startLine}–{row.endLine}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-6 space-y-6">
        {rows.map((row) => (
          <div key={`${row.id}-excerpt`}>
            <div className="border border-hairline bg-surface px-6 py-5">
              <p className="whitespace-pre-wrap font-courier text-[12px] leading-5 text-ink">
                {row.excerpt}
              </p>
            </div>
            <p className="mt-3 font-sans text-prose text-graphite">{row.reason}</p>
          </div>
        ))}
      </div>
      {notes.map((note) => (
        <p key={note} className="mt-6 max-w-[40rem] font-sans text-prose text-graphite">
          {note}
        </p>
      ))}
    </section>
  );
}
