# Build prompts — submit tonight

**Submit by 11:59 PM IST, 7 November 2026.** A public repo, a short video of the Switch room, and a README. Switch has to be in the video.

**Stop coding at 10:15 PM.** The last 90 minutes are the README, the push, the video, and the form.

Phase 0 is already built. The new visual source is the DevTeam Dossier: `stitch_devteamai/devteam_dossier/DESIGN.md` and six reference screens. That dossier is Phase 6. It is optional. It is not tonight’s work unless the room demo is already recorded.

Paste **one** prompt into a **new** chat. Do not attach `architecture.md`, `ProblemStatements.md`, the HTML screens, or the repo. Do not open `backend/.venv` or `stitch_devteamai/**/code.html`. Those files are what exceed the token limit.

| Clock    | Prompt | Move on when                                          |
| -------- | ------ | ----------------------------------------------------- |
| 7:20 PM  | A      | `test_intake_parser.py` is green, or the clock wins |
| 8:15 PM  | B      | Listener tests are green, or the clock wins           |
| 8:45 PM  | Live   | Mattermost shows a task id from the agent             |
| 9:30 PM  | C      | The room can show a file quote and a short diff       |
| 10:00 PM | D      | `approve` or `reject` is stored                   |
| 10:15 PM | Stop   | README, public repo, 2-minute video, submit           |

If a chat is still running with no file edits, stop it and use the recovery prompt at the bottom. Do not start the next letter in the same chat.

---

## Tonight A — intake

```text
RULES
Read only docs/implementation-plan.md lines 124-180, docs/edge-case.md lines 83-122, backend/app/domain/errors.py, backend/app/domain/models.py, backend/app/persistence/repository.py, backend/tests/conftest.py.
Do not search the repo. Do not open backend/.venv. Do not open stitch_devteamai. Do not rewrite app/domain or app/persistence.
Create only: backend/app/ports.py, backend/app/agent/__init__.py, backend/app/agent/parser.py, backend/app/services/__init__.py, backend/app/services/intake.py, backend/tests/test_intake_parser.py.
Ports are protocols only: Switch, repository, sandbox, GitHub read, GitHub write, reasoning.
Parser: approve, reject, and cancel count only when that ASCII word is the first token after the @mention. A mid-sentence "approve" is intake.
Intake persists RECEIVED through the existing StateMachine. Missing repository stays RECEIVED and the reply asks for it. One active task per room. A replayed (room_id, message_id) returns the same task. Default ref is main.
No socket, no model, no Docker, no dossier.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_intake_parser.py tests/test_state_machine.py -q
Print SLICE DONE and stop.
```

## Tonight B — listener

```text
RULES
Read only docs/implementation-plan.md lines 136-178, docs/architecture.md lines 219-243 and 523-541, docs/edge-case.md lines 63-79, backend/app/ports.py, backend/app/agent/parser.py, backend/app/services/intake.py.
Do not search the repo. Do not open backend/.venv or stitch_devteamai. No live network in the tests.
Create only: backend/app/agent/listener.py, backend/app/integrations/__init__.py, backend/app/integrations/switch_client.py, backend/tests/fakes.py, backend/tests/test_listener_filter.py, backend/tests/test_listener_resume.py.
Act only when payload.addressed is true. Ignore the agent's own posts. Dedup (room_id, message_id). Ping replies with the cursor. Reconnect uses the same connection_id and start_from. Events at or below the cursor are ignored.
Fake the transport. You may add httpx and websockets to backend/pyproject.toml. Do not add FastAPI.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_listener_filter.py tests/test_listener_resume.py -q
Print SLICE DONE and stop.
```

Then start Switch and Mattermost yourself. Post one checkout bug that mentions the agent. The reply must contain a task id. If it does not, fix only `listener.py` and `switch_client.py` in a new chat. Do not start C until that reply exists.

## Tonight C — one finding and one diff

```text
RULES
Read only docs/implementation-plan.md lines 182-220, backend/app/services/intake.py, backend/app/agent/listener.py, backend/app/domain/paths.py, backend/app/domain/models.py.
Do not search the repo. Do not open backend/.venv or stitch_devteamai. Do not add Docker or GitHub.
Create only: backend/app/integrations/repository.py, backend/app/services/investigation.py, backend/app/services/patch.py, backend/tests/test_demo_slice.py.
Read a local checkout only. Cap 8 files. Reject absolute paths and "..". Store excerpts that were actually read. Drop any other citation.
Store one unified diff under 400 lines, or transition to FAILED with unsafe_diff or invalid_diff. Do not invent a diff.
If no reasoning API key is set, do not call a model. Stay INVESTIGATING and return the stored excerpts.
Wire the listener so an issue runs intake, then this investigation. Return the room text to the caller. Do not open a socket in the test.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_demo_slice.py -q
Print SLICE DONE and stop.
```

## Tonight D — approval, then stop

```text
RULES
Read only docs/implementation-plan.md lines 276-318, docs/architecture.md lines 627-641, backend/app/agent/listener.py, backend/app/domain/errors.py, backend/app/persistence/repository.py.
Do not search the repo. Do not open backend/.venv or stitch_devteamai. No GitHub HTTP. No approve route.
Create only: backend/app/services/approval.py, backend/tests/test_approval_gate.py.
decide(task_id, decision, reviewer) requires a reviewer id that is not the agent and is in the participant list. State must be AWAITING_APPROVAL. Rejection requires a reason. A second decision writes nothing.
Wire approve, reject, and cancel from the listener.
When GITHUB_DELIVERY_TOKEN is empty, the room text says pull-request creation is not configured. Do not call GitHub.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_approval_gate.py -q
Print SLICE DONE and stop.
```

## Tonight E — README only

Do this in a new chat after D, and only if the clock is before 10:15 PM. If it is later, write the README yourself from the checklist below and do not open a chat.

```text
RULES
Read only backend/app/main.py if it exists, backend/app/agent/listener.py, and docs/architecture.md lines 799-835.
Do not search the repo. Do not open backend/.venv. Do not add features. Do not build the dossier.
Create or replace: README.md, .env.example, .gitignore.
.env.example lists empty names only: SWITCH_BASE_URL, SWITCH_AGENT_ID, SWITCH_AGENT_API_KEY, SWITCH_ROOM_ID, SWITCH_CONNECTION_ID, GITHUB_REPO, GITHUB_READ_TOKEN, GITHUB_DELIVERY_TOKEN, REASONING_BASE_URL, REASONING_API_KEY, REASONING_MODEL, DATABASE_PATH, DASHBOARD_TOKEN.
README covers: what the room does, how to install the backend, how to run pytest, how Switch and Mattermost are started from the Switch docs, and the exact issue message to post. State that the DevTeam Dossier and GitHub pull-request creation are not in this submission. State no timing or fix-rate claim.
.gitignore includes .env, backend/.venv, __pycache__, and *.db.
Print SLICE DONE and stop.
```

---

## What the video must show

1. A person posts in Mattermost, mentioning the agent, with a repository and the checkout HTTP 500.
2. The agent replies with a task id.
3. The agent names a file and quotes lines it read, then shows one diff.
4. The person sends `approve <task_id>` or `reject <task_id> <reason>`.
5. The agent confirms the decision and says pull-request creation is not configured.

The README must match that video. Do not mention a dashboard, a passing sandbox, or a GitHub URL unless that run is in the video.

## Submit checklist

- Public repository URL
- README with Switch setup and the issue message
- Demo video of the five steps above
- `docs/ProblemStatements.txt` already in the repo
- Form sent before 11:59 PM IST

---

## After the form is submitted — dossier

Do not start these until the form is sent, or until A–D are green and the clock is still before 9:00 PM. One dossier chat after 9:00 PM will cost the video. The reference is the paper dossier, not a generic dashboard.

Visual rules, from `docs/implementation-plan.md` lines 388-408. Do not open the HTML files. They contain an unused Material palette. `DESIGN.md` wins.

- Canvas `#f3f1ec`, surface `#faf9f6`, ink `#1a1814`, graphite `#6b6560`, hairline `#e3ddd4`, pine `#1e4d3a`, brick `#8c3a2f`
- Radius 2px. No shadow, blur, pills, or motion
- Section headers like `01 / TIMELINE`: IBM Plex Sans 11px, weight 600, tracking 0.12em, graphite, hairline under the header
- Titles Newsreader. Prose IBM Plex Sans. Task ids, paths, diffs, and pytest output Courier Prime
- Pine and brick are type and 2px ticks, not filled banners
- No approve button. Decisions happen in Switch

### Dossier 1 — read API

```text
RULES
Read only docs/implementation-plan.md lines 520-528, docs/architecture.md lines 670-689, docs/edge-case.md lines 270-287, backend/app/persistence/repository.py, backend/app/domain/errors.py.
Do not search the repo. Do not open backend/.venv or stitch_devteamai. No approve, reject, intake, or delivery route.
Create only: backend/app/api/__init__.py, backend/app/api/schemas.py, backend/app/api/routes.py, backend/app/main.py, backend/tests/test_api_dashboard.py.
Add fastapi to backend/pyproject.toml if it is missing.
GET /health is open. GET /api/v1/tasks and the nested read routes require the dashboard token. Unknown id returns {"error": {"code": "task_not_found", "message", "task_id"}}. List is newest first for the configured room.
A stolen dashboard token cannot approve, because those routes do not exist.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_api_dashboard.py -q
Print SLICE DONE and stop.
```

### Dossier 2 — Open work and the empty room

```text
RULES
Read only docs/implementation-plan.md lines 382-439 and stitch_devteamai/devteam_dossier/DESIGN.md lines 116-203.
Do not open any code.html file. Do not open node_modules. Do not add an approve control.
Create the Next.js App Router app described at docs/implementation-plan.md lines 482-508, but only the shell, the index, and the empty state:
- frontend/app/layout.tsx, page.tsx, tailwind.config.ts
- frontend/components/TaskRow.tsx
- frontend/lib/states.ts, frontend/lib/format.ts
Fonts through next/font: Newsreader, IBM Plex Sans, Courier Prime.
Header is 56px with a bottom hairline. Left: DEVTEAM and the room label. Right: SWITCH as an underlined pine link only when NEXT_PUBLIC_SWITCH_ROOM_URL is set. Footer says the record is read-only and sign-off happens in Switch.
Route / with rows: title "Open work." Section "01 / ACTIVE DOSSIER QUEUE". Row is 64px: 2px tick, 6-character id, title link, priority, state, relative time. AWAITING_APPROVAL tick and state are pine. FAILED tick and state are brick. Other states use ink and no tick. The link uses the full UUID.
Route / with an empty list: "No tasks in this room yet." Tell the reader to mention @devteam in Switch with a repository and the error.
Data is a fixture in this slice. Do not call FastAPI yet.
npm run build in frontend must succeed.
Print SLICE DONE and stop.
```

### Dossier 3 — case file

```text
RULES
Read only docs/implementation-plan.md lines 440-518 and frontend/app/page.tsx, frontend/app/layout.tsx, frontend/lib/states.ts.
Do not open any code.html file. Do not open node_modules. Do not add a button, form, or checkbox.
Create only: frontend/app/tasks/[id]/page.tsx, frontend/components/Timeline.tsx, frontend/components/EvidenceList.tsx, frontend/components/DiffView.tsx, frontend/components/ValidationLog.tsx, frontend/components/DecisionPanel.tsx, frontend/components/UnknownTask.tsx, frontend/lib/diff.ts, frontend/tests/dossier.test.tsx.
One route, four states, fixture data:
- Existing task: meta line with the full id, Newsreader title, summary, then only the sections that have rows. Order: 01 Timeline, 02 Evidence, 03 Patch, 04 Validation, 05 Decision.
- Unknown id: "This task is not in the room." One link back to Open work.
- FAILED: brick tick, brick FAILED, last event payload as a line of type on the paper canvas. Not a filled banner.
- AWAITING_APPROVAL decision copy: "Waiting for a person in the room." Show the approve and reject commands as selectable text. Pull request reads "not created".
Omit incident ref, revisions, assignee, constraints, and subsystem. The API does not store them.
Diff added lines use a 2px pine tick. Removed lines are brick type. Stdout is a pre. A fixture stdout that contains a script tag renders as text.
dossier.test.tsx covers the empty index, pine and brick ticks, an unknown id, the failed reason line, the script-tag stdout, and the absence of any approve control.
npm run build, then the frontend test command, must succeed.
Print SLICE DONE and stop.
```

### Dossier 4 — wire the pages to FastAPI

```text
RULES
Read only frontend/lib/format.ts, frontend/app/tasks/[id]/page.tsx, backend/app/api/routes.py, and docs/implementation-plan.md lines 462-480.
Do not open code.html or node_modules. Do not put DASHBOARD_TOKEN in a NEXT_PUBLIC_ variable.
Create only: frontend/lib/api.ts, frontend/app/api/tasks/route.ts, frontend/app/api/tasks/[id]/route.ts, and a client poller used by the index and the case file.
Server route handlers call FastAPI with API_BASE_URL and DASHBOARD_TOKEN. The browser polls the same-origin handler every 3 seconds while the state is non-terminal, and stops on APPROVED, REJECTED, PR_CREATED, FAILED, and CANCELLED. A failed poll keeps the last good record.
The detail handler may join the read routes into one JSON object. It must not call approve, reject, intake, or delivery.
First paint is a Server Component. The poller is a client island. The waiting index shows "01 / TASK INDEX" and the canvas, with no spinner.
npm run build must succeed.
Print SLICE DONE and stop.
```

### Pull request — only with a real token

```text
RULES
Read only backend/app/services/approval.py and backend/app/ports.py.
Do not search the repo. If GITHUB_DELIVERY_TOKEN is unset, print NOT CONFIGURED and stop. Do not invent a token. Do not merge.
Create only: backend/app/integrations/github.py, backend/app/services/delivery.py, backend/tests/test_delivery.py.
Empty token: zero writes, approval row kept, state stays APPROVED.
Set token: the fake records branch devteam/<task_id>, one commit of the stored diff, one pull request into git_ref, then PR_CREATED.
Any state other than APPROVED raises approval_required before a write. An agent reviewer fails the same way.
From backend run: .\.venv\Scripts\python.exe -m pytest tests/test_delivery.py tests/test_approval_gate.py -q
Print SLICE DONE and stop.
```

---

## Recovery

Stop the stuck chat. Open a new chat. Paste this. Do not attach the old transcript.

```text
RECOVERY
The previous turn was interrupted. Do not restart the slice. Do not re-read the docs. Do not search the repo. Do not open backend/.venv or any code.html file.

Slice: <A, B, C, D, or a dossier number>
Already created: <files>
Still missing: <one file or one test>

Read only those files. Finish the missing part.
From backend, if this slice has a pytest file:
.\.venv\Scripts\python.exe -m pytest <one test file> -q

If that command already passes, print SLICE DONE and stop.
Your first tool call must read the single file named above. If you need a second file, stop and ask.
```

## Do not paste

- “Implement Phase 6” or “build the dossier and the backend.”
- Any file under `stitch_devteamai/**/code.html`.
- `DESIGN.md` in full. The dossier prompts name the line range.
- More than one letter in the same chat.
