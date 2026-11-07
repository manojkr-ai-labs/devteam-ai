import React, { type ReactNode } from "react";

export type ApprovalModel = {
  decision: "approved" | "rejected";
  reviewerName: string;
  reviewerId: string;
  decidedAt: string;
  reason: string | null;
};

export type PullRequestModel = {
  url: string;
  number: number;
};

export type DecisionModel = {
  state: string;
  taskId: string;
  hasPatch: boolean;
  approval: ApprovalModel | null;
  pullRequest: PullRequestModel | null;
};

const SHOWN = new Set([
  "AWAITING_APPROVAL",
  "APPROVED",
  "REJECTED",
  "PR_CREATED",
  "FAILED",
]);

function Field({ label, children }: { label: string; children: string }) {
  return (
    <>
      <dt className="font-sans text-meta text-graphite">{label}</dt>
      <dd className="font-sans text-meta text-ink">{children}</dd>
    </>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <section id="decision" className="mt-12" aria-labelledby="decision-title">
      <div className="border-b border-hairline pb-3">
        <h2
          id="decision-title"
          className="font-sans text-section font-semibold text-graphite"
        >
          05 / DECISION
        </h2>
      </div>
      <div className="mt-6 border border-hairline bg-surface px-6 py-5">{children}</div>
    </section>
  );
}

function dashes() {
  return (
    <dl className="mt-6 grid grid-cols-[9rem_minmax(0,1fr)] gap-y-2 max-[719px]:grid-cols-1">
      <Field label="Reviewer">—</Field>
      <Field label="Decided">—</Field>
      <Field label="Pull request">not created</Field>
    </dl>
  );
}

export function DecisionPanel({ record }: { record: DecisionModel }) {
  if (!SHOWN.has(record.state)) return null;

  if (record.state === "AWAITING_APPROVAL") {
    return (
      <Shell>
        <p className="font-sans text-prose text-ink">Waiting for a person in the room.</p>
        <div className="mt-4 space-y-2">
          <p className="select-text font-courier text-meta text-ink">{`@devteam approve ${record.taskId}`}</p>
          <p className="select-text font-courier text-meta text-ink">{`@devteam reject ${record.taskId} reason`}</p>
        </div>
        {dashes()}
      </Shell>
    );
  }

  if (record.state === "FAILED" && !record.hasPatch) {
    return (
      <Shell>
        <p className="font-sans text-prose text-ink">Nothing to approve.</p>
        <p className="mt-3 font-sans text-prose text-graphite">
          The task ended before a hypothesis or a diff.
        </p>
        {dashes()}
      </Shell>
    );
  }

  if (record.state === "PR_CREATED" && record.pullRequest) {
    return (
      <Shell>
        <p className="font-sans text-prose text-ink">
          <a
            href={record.pullRequest.url}
            className="font-courier text-meta text-pine underline decoration-pine decoration-1 underline-offset-4"
          >
            {record.pullRequest.url}
          </a>
          <span className="ml-4 font-courier text-meta text-ink">{record.pullRequest.number}</span>
        </p>
      </Shell>
    );
  }

  if (
    (record.state === "APPROVED" || record.state === "REJECTED") &&
    record.approval
  ) {
    return (
      <Shell>
        <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-y-2 max-[719px]:grid-cols-1">
          <Field label="Decision">{record.approval.decision}</Field>
          <Field label="Reviewer">{record.approval.reviewerName}</Field>
          <Field label="Reviewer id">{record.approval.reviewerId}</Field>
          <Field label="Decided">{record.approval.decidedAt}</Field>
          {record.state === "REJECTED" && record.approval.reason ? (
            <Field label="Reason">{record.approval.reason}</Field>
          ) : null}
        </dl>
      </Shell>
    );
  }

  return null;
}
