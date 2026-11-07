import React, { Fragment, type ReactNode } from "react";

export type ValidationRunModel = {
  id: string;
  command: string;
  exitCode: number | null;
  status: "passed" | "failed" | "error";
  stdout: string;
  stderr: string;
};

const STATUS_TONE = {
  passed: "text-pine",
  failed: "text-brick",
  error: "text-brick",
} as const;

function colorize(text: string): ReactNode[] {
  return text.split(/(PASSED|FAILED)/g).map((part, index) => {
    if (part === "PASSED") {
      return (
        <span key={index} className="text-pine">
          {part}
        </span>
      );
    }
    if (part === "FAILED") {
      return (
        <span key={index} className="text-brick">
          {part}
        </span>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function stream(text: string) {
  return (
    <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap break-words border-l border-hairline bg-canvas px-4 py-3 font-courier text-[12px] leading-5 text-ink">
      {colorize(text)}
    </pre>
  );
}

export function ValidationLog({ runs }: { runs: ValidationRunModel[] }) {
  if (runs.length === 0) return null;

  return (
    <section id="validation" className="mt-12" aria-labelledby="validation-title">
      <div className="border-b border-hairline pb-3">
        <h2
          id="validation-title"
          className="font-sans text-section font-semibold text-graphite"
        >
          04 / VALIDATION
        </h2>
      </div>
      <div className="mt-6 space-y-8">
        {runs.map((run) => (
          <article key={run.id}>
            <p className="font-courier text-[12px] leading-5 text-ink">{run.command}</p>
            <p className="mt-2 font-sans text-meta text-ink">
              <span className="font-courier">exit {run.exitCode ?? "—"}</span>
              <span className="mx-3 text-graphite" aria-hidden="true">
                /
              </span>
              <span className={STATUS_TONE[run.status]}>{run.status}</span>
            </p>
            {stream(run.stdout)}
            {run.stderr !== "" ? stream(run.stderr) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
