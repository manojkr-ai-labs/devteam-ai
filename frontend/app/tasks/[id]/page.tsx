import type { Metadata } from "next";
import React from "react";

import { DecisionPanel, type DecisionModel } from "@/components/DecisionPanel";
import { DiffView, type PatchModel } from "@/components/DiffView";
import { EvidenceList, type FindingModel } from "@/components/EvidenceList";
import { Timeline, type TimelineEvent } from "@/components/Timeline";
import { UnknownTask } from "@/components/UnknownTask";
import { ValidationLog, type ValidationRunModel } from "@/components/ValidationLog";
import { relativeTime } from "@/lib/format";
import { stateTone, tickFor, type StateTone } from "@/lib/states";

export const dynamic = "force-dynamic";

type DossierEvent = {
  id: string;
  at: string;
  actor: string;
  line: string;
  toState: string;
  payload: Record<string, string>;
};

type Dossier = {
  id: string;
  title: string;
  summary: string;
  priority: string | null;
  state: string;
  repository: string | null;
  updatedAt: string;
  events: DossierEvent[];
  findings: FindingModel[];
  patch: PatchModel | null;
  validation: ValidationRunModel[];
  approval: DecisionModel["approval"];
  pullRequest: DecisionModel["pullRequest"];
};

const TONE: Record<StateTone, string> = {
  pine: "text-pine",
  brick: "text-brick",
  ink: "text-ink",
};

const CHECKOUT_DIFF = [
  "diff --git a/app/checkout.py b/app/checkout.py",
  "index 4f1b8a9..c0ffee1 100644",
  "--- a/app/checkout.py",
  "+++ b/app/checkout.py",
  "@@ -40,6 +40,7 @@ def charge(session):",
  '     cart_id = session.get("cart_id")',
  "-    if cart_id is None:",
  '-        raise CheckoutError("missing cart")',
  "+    if not cart_id:",
  "+        cart_id = ensure_cart(session)",
  "     return charge_cart(cart_id)",
].join("\n");

const AWAITING_ID = "8f3c1a2b-4c5d-4e6f-a7b8-c9d0e1f20001";
const INVESTIGATING_ID = "1c02e93a-4b5c-4d6e-8f70-112233445501";
const PR_ID = "9ab14d77-1111-4222-8333-444455556601";
const FAILED_ID = "44e0b7aa-bbbb-4ccc-8ddd-eeeeffff0001";

const DOSSIERS: Dossier[] = [
  {
    id: AWAITING_ID,
    title: "Checkout API returns HTTP 500 after user login",
    summary:
      "Login leaves the session without a cart id. Checkout then raises, and the API answers 500.",
    priority: "high",
    state: "AWAITING_APPROVAL",
    repository: "shop/checkout",
    updatedAt: "2026-11-07T13:40:00Z",
    events: [
      {
        id: "11111111-1111-4111-8111-111111111101",
        at: "2026-11-07T13:10:00Z",
        actor: "devteam",
        line: "Issue received from the room.",
        toState: "RECEIVED",
        payload: {},
      },
      {
        id: "11111111-1111-4111-8111-111111111102",
        at: "2026-11-07T13:18:00Z",
        actor: "devteam",
        line: "Classified as a bug.",
        toState: "TRIAGED",
        payload: {},
      },
      {
        id: "11111111-1111-4111-8111-111111111103",
        at: "2026-11-07T13:24:00Z",
        actor: "devteam",
        line: "Checkout reads cart_id before login stores it.",
        toState: "INVESTIGATING",
        payload: {},
      },
      {
        id: "11111111-1111-4111-8111-111111111104",
        at: "2026-11-07T13:31:00Z",
        actor: "devteam",
        line: "Diff proposed for the session cart.",
        toState: "PATCH_PROPOSED",
        payload: {},
      },
      {
        id: "11111111-1111-4111-8111-111111111105",
        at: "2026-11-07T13:36:00Z",
        actor: "system",
        line: "pytest -q exited 0.",
        toState: "VALIDATING",
        payload: {},
      },
      {
        id: "11111111-1111-4111-8111-111111111106",
        at: "2026-11-07T13:40:00Z",
        actor: "system",
        line: "Waiting on a person in the room.",
        toState: "AWAITING_APPROVAL",
        payload: {},
      },
    ],
    findings: [
      {
        id: "22222222-2222-4222-8222-222222222201",
        hypothesis:
          "Checkout treats a missing cart id as a server error instead of an empty cart.",
        uncertainties:
          "A session expiry can also drop the key. That path was not in the trace.",
        evidence: [
          {
            id: "33333333-3333-4333-8333-333333333301",
            path: "app/checkout.py",
            startLine: 40,
            endLine: 44,
            excerpt: [
              "def charge(session):",
              '    cart_id = session.get("cart_id")',
              "    if cart_id is None:",
              '        raise CheckoutError("missing cart")',
            ].join("\n"),
            reason: "charge raises when login never stored cart_id, and the API returns 500.",
          },
          {
            id: "33333333-3333-4333-8333-333333333302",
            path: "app/session.py",
            startLine: 12,
            endLine: 18,
            excerpt: [
              "def login(user):",
              "    session = {}",
              '    session["user_id"] = user.id',
              "    return session",
            ].join("\n"),
            reason: "login writes user_id and leaves cart_id unset.",
          },
        ],
      },
    ],
    patch: {
      summary: "Create the cart when the session has a user and no cart id.",
      affectedFiles: ["app/checkout.py"],
      diff: CHECKOUT_DIFF,
    },
    validation: [
      {
        id: "44444444-4444-4444-8444-444444444401",
        command: "pytest -q",
        exitCode: 0,
        status: "passed",
        stdout: [
          "<script>alert(1)</script>",
          "PASSED tests/test_checkout.py::test_charge_uses_session_cart",
        ].join("\n"),
        stderr: "",
      },
    ],
    approval: null,
    pullRequest: null,
  },
  {
    id: INVESTIGATING_ID,
    title: "Login never writes cart_id onto the session",
    summary: "The session is written at login without cart_id. The file that should set it is still open.",
    priority: "medium",
    state: "INVESTIGATING",
    repository: "shop/checkout",
    updatedAt: "2026-11-07T13:22:00Z",
    events: [
      {
        id: "55555555-5555-4555-8555-555555555501",
        at: "2026-11-07T13:04:00Z",
        actor: "devteam",
        line: "Issue received from the room.",
        toState: "RECEIVED",
        payload: {},
      },
      {
        id: "55555555-5555-4555-8555-555555555502",
        at: "2026-11-07T13:12:00Z",
        actor: "devteam",
        line: "Classified as a bug.",
        toState: "TRIAGED",
        payload: {},
      },
      {
        id: "55555555-5555-4555-8555-555555555503",
        at: "2026-11-07T13:22:00Z",
        actor: "devteam",
        line: "Reading the login writer.",
        toState: "INVESTIGATING",
        payload: {},
      },
    ],
    findings: [
      {
        id: "66666666-6666-4666-8666-666666666601",
        hypothesis: "login stores user_id and never assigns cart_id.",
        uncertainties: "",
        evidence: [
          {
            id: "77777777-7777-4777-8777-777777777701",
            path: "app/session.py",
            startLine: 12,
            endLine: 16,
            excerpt: 'session["user_id"] = user.id',
            reason: "The writer stops after user_id.",
          },
        ],
      },
    ],
    patch: null,
    validation: [],
    approval: null,
    pullRequest: null,
  },
  {
    id: PR_ID,
    title: "Payment webhook signature mismatch",
    summary:
      "The webhook compared the signature against the raw body with the wrong encoding. The patch is on the pull request.",
    priority: "low",
    state: "PR_CREATED",
    repository: "shop/payments",
    updatedAt: "2026-11-06T15:00:00Z",
    events: [
      {
        id: "88888888-8888-4888-8888-888888888801",
        at: "2026-11-06T14:10:00Z",
        actor: "devteam",
        line: "Issue received from the room.",
        toState: "RECEIVED",
        payload: {},
      },
      {
        id: "88888888-8888-4888-8888-888888888802",
        at: "2026-11-06T14:40:00Z",
        actor: "system",
        line: "Pull request opened.",
        toState: "PR_CREATED",
        payload: {},
      },
    ],
    findings: [],
    patch: {
      summary: "Decode the webhook body before the signature compare.",
      affectedFiles: ["app/webhooks.py"],
      diff: [
        "diff --git a/app/webhooks.py b/app/webhooks.py",
        "--- a/app/webhooks.py",
        "+++ b/app/webhooks.py",
        "@@ -8,3 +8,3 @@ def verify(body, signature):",
        "-    digest = sign(body)",
        "+    digest = sign(body.decode())",
        "     return digest == signature",
      ].join("\n"),
    },
    validation: [
      {
        id: "99999999-9999-4999-8999-999999999901",
        command: "pytest -q",
        exitCode: 0,
        status: "passed",
        stdout: "PASSED tests/test_webhook.py\n",
        stderr: "",
      },
    ],
    approval: {
      decision: "approved",
      reviewerName: "A. Okonkwo",
      reviewerId: "user-okonkwo",
      decidedAt: "2026-11-06T14:50:00Z",
      reason: null,
    },
    pullRequest: {
      url: "https://github.com/shop/payments/pull/18",
      number: 18,
    },
  },
  {
    id: FAILED_ID,
    title: "Checkout suite killed at the sandbox timeout",
    summary: "The sandbox killed the suite before it stored a hypothesis or a diff.",
    priority: "critical",
    state: "FAILED",
    repository: "shop/checkout",
    updatedAt: "2026-11-06T15:04:00Z",
    events: [
      {
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
        at: "2026-11-06T14:40:00Z",
        actor: "devteam",
        line: "Issue received from the room.",
        toState: "RECEIVED",
        payload: {},
      },
      {
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
        at: "2026-11-06T15:04:00Z",
        actor: "system",
        line: "The sandbox killed the suite.",
        toState: "FAILED",
        payload: { stage: "validation", error: "timeout" },
      },
    ],
    findings: [],
    patch: null,
    validation: [],
    approval: null,
    pullRequest: null,
  },
];

function findDossier(id: string): Dossier | null {
  return DOSSIERS.find((task) => task.id === id) ?? null;
}

function payloadLine(payload: Record<string, string>): string {
  return Object.entries(payload)
    .map(([key, value]) => `${key} ${value}`)
    .join(" \u00b7 ");
}

function timelineEvents(events: DossierEvent[]): TimelineEvent[] {
  return events.map((event) => ({
    id: event.id,
    at: event.at,
    actor: event.actor,
    line: event.line,
    failed: event.toState === "FAILED",
  }));
}

type TaskPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: TaskPageProps): Promise<Metadata> {
  const { id } = await params;
  const task = findDossier(id);
  return { title: task ? task.title : "This task is not in the room." };
}

export default async function TaskPage({ params }: TaskPageProps) {
  const { id } = await params;
  const task = findDossier(id);
  if (!task) return <UnknownTask />;

  const now = new Date();
  const tick = tickFor(task.state);
  const tone = stateTone(task.state);
  const last = task.events[task.events.length - 1];
  const reason = task.state === "FAILED" && last ? payloadLine(last.payload) : "";

  return (
    <div className="py-12">
      <p className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="font-courier text-meta text-ink">{task.id}</span>
        {tick === "none" ? null : (
          <span aria-hidden="true" className="flex h-6 items-center">
            <span
              data-tick={tick}
              className={`block h-6 w-[2px] ${tick === "pine" ? "bg-pine" : "bg-brick"}`}
            />
          </span>
        )}
        <span
          data-state={task.state}
          className={`font-sans text-section font-semibold ${TONE[tone]}`}
        >
          {task.state}
        </span>
        {task.repository ? (
          <span className="font-courier text-meta text-graphite">{task.repository}</span>
        ) : null}
        <span className="font-sans text-meta text-graphite">{task.priority ?? "—"}</span>
        <time
          dateTime={task.updatedAt}
          title={task.updatedAt}
          className="font-sans text-meta text-graphite"
        >
          {relativeTime(task.updatedAt, now)}
        </time>
      </p>
      <h1 className="mt-8 font-newsreader text-display font-normal tracking-[-0.02em] text-ink">
        {task.title}
      </h1>
      <p className="mt-4 max-w-[40rem] font-sans text-prose text-ink">{task.summary}</p>
      {reason !== "" ? (
        <p data-reason="failed" className="mt-6 bg-canvas font-sans text-prose text-brick">
          {reason}
        </p>
      ) : null}
      <Timeline events={timelineEvents(task.events)} />
      <EvidenceList findings={task.findings} />
      <DiffView patch={task.patch} />
      <ValidationLog runs={task.validation} />
      <DecisionPanel
        record={{
          state: task.state,
          taskId: task.id,
          hasPatch: task.patch !== null,
          approval: task.approval,
          pullRequest: task.pullRequest,
        }}
      />
    </div>
  );
}
