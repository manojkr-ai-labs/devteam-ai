import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TaskPage from "../app/tasks/[id]/page";

const AWAITING = "8f3c1a2b-4c5d-4e6f-a7b8-c9d0e1f20001";
const INVESTIGATING = "1c02e93a-4b5c-4d6e-8f70-112233445501";
const FAILED = "44e0b7aa-bbbb-4ccc-8ddd-eeeeffff0001";
const UNKNOWN = "00000000-0000-4000-8000-000000009999";

const here = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(join(here, "../app/page.tsx"), "utf8");
const rowSource = readFileSync(join(here, "../components/TaskRow.tsx"), "utf8");

async function renderTask(id: string): Promise<string> {
  const node = await TaskPage({ params: Promise.resolve({ id }) });
  return renderToStaticMarkup(node as ReactElement);
}

function assertNoApproveControl(html: string) {
  assert.equal(/<button\b/i.test(html), false);
  assert.equal(/<form\b/i.test(html), false);
  assert.equal(/<input\b/i.test(html), false);
  assert.equal(/<textarea\b/i.test(html), false);
  assert.equal(/<select\b/i.test(html), false);
  assert.equal(/checkbox/i.test(html), false);
}

describe("dossier", () => {
  it("covers the empty index", () => {
    assert.match(pageSource, /No tasks in this room yet\./);
    assert.match(pageSource, /@devteam/);
    assert.match(pageSource, /repository and the error/);
    assert.match(pageSource, /tasks\.length === 0/);
    assert.match(pageSource, /Open work\./);
    assert.match(pageSource, /01 \/ ACTIVE DOSSIER QUEUE/);
    assert.equal(pageSource.includes("<button"), false);
    assert.equal(pageSource.includes("<form"), false);
    assert.equal(pageSource.includes("<input"), false);
  });

  it("renders pine and brick ticks", async () => {
    assert.match(rowSource, /data-tick=\{tick\}/);
    assert.match(rowSource, /bg-pine/);
    assert.match(rowSource, /bg-brick/);
    assert.match(rowSource, /text-pine/);
    assert.match(rowSource, /text-brick/);

    const awaiting = await renderTask(AWAITING);
    assert.match(awaiting, /data-tick="pine"/);
    assert.match(awaiting, /data-state="AWAITING_APPROVAL"/);
    assert.match(awaiting, /text-pine/);
    assert.match(awaiting, new RegExp(AWAITING));

    const failed = await renderTask(FAILED);
    assert.match(failed, /data-tick="brick"/);
    assert.match(failed, /data-state="FAILED"/);
    assert.match(failed, /text-brick/);

    const added = awaiting.match(/data-line="add"[\s\S]*?bg-pine/);
    const removed = awaiting.match(/data-line="remove"[\s\S]*?text-brick/);
    assert.ok(added);
    assert.ok(removed);
    assert.match(awaiting, /\+2 \/ \u22122/);
  });

  it("renders an unknown id", async () => {
    const html = await renderTask(UNKNOWN);
    assert.match(html, /This task is not in the room\./);
    assert.match(html, /href="\/"/);
    assert.match(html, />Open work</);
    assert.equal(html.match(/<a\b/g)?.length, 1);
    assert.equal(html.includes("01 / TIMELINE"), false);
    assertNoApproveControl(html);
  });

  it("renders the failed reason as a line of type", async () => {
    const html = await renderTask(FAILED);
    assert.match(html, /data-reason="failed"[^>]*class="[^"]*bg-canvas[^"]*text-brick/);
    assert.equal(/data-reason="failed"[^>]*bg-brick/.test(html), false);
    assert.match(html, /stage validation \u00b7 error timeout/);
    assert.match(html, /Nothing to approve\./);
    assert.match(html, /ended before a hypothesis or a diff/);
    assert.match(html, /not created/);
    assert.match(html, /01 \/ TIMELINE/);
    assert.match(html, /05 \/ DECISION/);
    assert.equal(html.includes("02 / EVIDENCE"), false);
    assert.equal(html.includes("03 / PATCH"), false);
    assert.equal(html.includes("04 / VALIDATION"), false);
    assertNoApproveControl(html);
  });

  it("renders a script tag in stdout as text", async () => {
    const html = await renderTask(AWAITING);
    assert.match(html, /<pre[\s>]/);
    assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
    assert.equal(/<script/i.test(html), false);
    assert.match(html, /<span class="text-pine">PASSED<\/span>/);

    const timeline = html.indexOf("01 / TIMELINE");
    const evidence = html.indexOf("02 / EVIDENCE");
    const patch = html.indexOf("03 / PATCH");
    const validation = html.indexOf("04 / VALIDATION");
    const decision = html.indexOf("05 / DECISION");
    assert.ok(timeline < evidence);
    assert.ok(evidence < patch);
    assert.ok(patch < validation);
    assert.ok(validation < decision);
  });

  it("has no approve control", async () => {
    const html = await renderTask(AWAITING);
    assertNoApproveControl(html);
    assert.match(html, /Waiting for a person in the room\./);
    assert.match(html, new RegExp(`@devteam approve ${AWAITING}`));
    assert.match(html, new RegExp(`@devteam reject ${AWAITING} reason`));
    assert.match(html, />not created</);
    assert.equal(html.includes("<button"), false);

    const investigating = await renderTask(INVESTIGATING);
    assert.equal(investigating.includes("05 / DECISION"), false);
    assert.match(investigating, /01 \/ TIMELINE/);
    assert.match(investigating, /02 \/ EVIDENCE/);
    assertNoApproveControl(investigating);
  });
});
