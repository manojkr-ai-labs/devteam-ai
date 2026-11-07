# DevTeam AI Edge Cases

**Product:** Collaborative Software Incident Resolution Platform  
**Sources:** [architecture.md](./architecture.md), [ProblemStatements.md](./ProblemStatements.md)  
**Version:** 4.0  
**Status:** MVP edge-case catalog

`docs/implementation-plan.md` was not in the repository when this catalog was written. Every case below follows the architecture: Switch is the only collaboration channel, SQLite is the source of truth for state and approval, and a pull request exists only after a stored human approval.

Each case names the required outcome and the test that should lock it in. Severity:

| Severity | Meaning |
|---|---|
| S0 | Breaks the demo, the approval gate, or evidence integrity. |
| S1 | Wrong task state, a stuck room, or a misleading result. |
| S2 | Recoverable friction. The task stays explainable. |

---

## Contents

1. [Handling rules](#1-handling-rules)
2. [Switch connection and room messages](#2-switch-connection-and-room-messages)
3. [Intake and command parsing](#3-intake-and-command-parsing)
4. [One active task](#4-one-active-task)
5. [State machine](#5-state-machine)
6. [Reasoning provider](#6-reasoning-provider)
7. [Investigation and evidence](#7-investigation-and-evidence)
8. [Patch safety](#8-patch-safety)
9. [Sandbox and test evidence](#9-sandbox-and-test-evidence)
10. [Approval](#10-approval)
11. [Delivery](#11-delivery)
12. [Restart and persistence](#12-restart-and-persistence)
13. [HTTP API and dashboard](#13-http-api-and-dashboard)
14. [Security boundaries](#14-security-boundaries)
15. [Demonstration scenario](#15-demonstration-scenario)
16. [Cases the MVP leaves alone](#16-cases-the-mvp-leaves-alone)
17. [Test map](#17-test-map)

---

## 1. Handling rules

These rules resolve situations the architecture names in more than one place.

| Rule | Behavior |
|---|---|
| State first | A stage persists its row and transition, then posts to the room. A failed `post_message` is retried. The stage is not run again to “resend” a model call or a test run. |
| Command shape | After the mention, the first token decides. `approve`, `reject`, and `cancel` are commands. Any other addressed text is issue content or a follow-up on the active task. |
| Task id required | `approve`, `reject`, and `cancel` include the task id. The listener does not substitute “the current task”. |
| Waiting states survive | `RECEIVED` (repo still missing), `INVESTIGATING` (no citable evidence yet), and `AWAITING_APPROVAL` stay as stored across a restart. |
| In-flight validation does not survive | A restart during `VALIDATING` with no exit code stores `validation_run.status = error` and moves the task to `FAILED` with reason `interrupted`. |
| Other in-flight stages do not auto-resume | On startup the listener posts the current state of any non-terminal task. It does not call the reasoning provider again until a new addressed follow-up arrives. |
| Pin the commit | `resolve` stores the commit SHA that was read. Search, patch apply, tests, and the pull request use that SHA. |
| Unsafe model output is a hard failure | A schema-invalid response is not retried. A schema-valid diff that fails the path, size, or emptiness checks is not stored. The task goes to `FAILED` with the validator reason. |
| Completed tests always reach the human | Pytest exit 0 is `passed`. Pytest exit non-zero is `failed`. Both move to `AWAITING_APPROVAL` and the room quotes the stored output. |
| Sandbox failure is `FAILED` | A missing image, a kill, a timeout, or an empty exit code is `validation_run.status = error` and state `FAILED`. |
| Empty delivery token | State `APPROVED` stands. The room says pull-request creation is not configured. GitHub is not called. |
| Delivery write order | GitHub is called only after the approval guard. The `pull_request` row and the `PR_CREATED` transition commit together. A repeated delivery looks up an existing pull request for `devteam/<task_id>` before opening another. |

---

## 2. Switch connection and room messages

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-SW-01 | S0 | WebSocket drops while a stage is running. | Reconnect with the same `connection_id`, the last cursor, and `start_from`. The in-process stage keeps its task lock and finishes one transition. | `test_listener_resume.py` |
| EC-SW-02 | S0 | Switch replays a `message` with the same `(room_id, message_id)`. | Dedup returns the original task. No second intake, approval, or test run. | `test_listener_resume.py` |
| EC-SW-03 | S0 | A `message` has `addressed = false`. | No task, no state change, no room reply. | `test_listener_filter.py` |
| EC-SW-04 | S0 | The event sender is this agent. | The listener ignores it, including echoes of its own posts. | `test_listener_filter.py` |
| EC-SW-05 | S1 | A ping arrives during pytest. | The listener answers with a pong that includes the cursor. The sandbox is not cancelled by the ping. | `test_listener_resume.py` |
| EC-SW-06 | S1 | The socket opens without the demo room on the URL. | The listener claims `SWITCH_ROOM_ID` before acting. Events from before the claim are not treated as a fresh issue. | `test_listener_resume.py` |
| EC-SW-07 | S1 | `post_message` fails after the task is already `TRIAGED`. | Retry the post. Classification is unchanged. `classify` is not called again. | `test_listener_resume.py` |
| EC-SW-08 | S1 | The agent API key is rejected. | The HTTP API stays up. The listener backs off and logs an authentication failure. No task is created. | `test_listener_resume.py` |
| EC-SW-09 | S1 | Switch sends a burst of events after resume. | Events at or below the stored cursor are ignored. Newer addressed messages are handled once, in `seq` order. | `test_listener_resume.py` |
| EC-SW-10 | S2 | The issue body is empty and a text attachment is present. | The listener fetches that attachment and uses it as logs. A failed fetch leaves the task in `RECEIVED` and asks for a paste. | `test_intake_parser.py` |
| EC-SW-11 | S2 | The attachment is binary. | The file is not sent to the reasoning provider. The room asks for a text log. | `test_intake_parser.py` |
| EC-SW-12 | S1 | `list_participants` fails during an approval message. | No approval row is written. The room asks the reviewer to retry. State stays `AWAITING_APPROVAL`. | `test_approval_gate.py` |
| EC-SW-13 | S2 | Room instructions contradict a human `approve`. | The human command is the decision. Room instructions do not approve or reject a task. | `test_approval_gate.py` |

---

## 3. Intake and command parsing

The parser recognizes a command only when the first token after the mention is `approve`, `reject`, or `cancel`, compared case-insensitively as those ASCII words.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-IN-01 | S0 | Addressed issue with description and logs, and no repository. | Create the task in `RECEIVED`. Ask for the repository. Do not call triage. | `test_intake_parser.py` |
| EC-IN-02 | S1 | A later addressed message supplies `Repo:` for the task still in `RECEIVED`. | Fill the repository on that task and continue. Do not open a second task. | `test_intake_parser.py` |
| EC-IN-03 | S2 | `Ref` is omitted and the repository resolves. | Store `git_ref = main`, then pin the SHA that `main` resolves to. | `test_intake_parser.py` |
| EC-IN-04 | S1 | The body is a GitHub URL plus a problem statement, without the word `investigate`. | Treat it as intake. | `test_intake_parser.py` |
| EC-IN-05 | S0 | The body is only `@devteam`. | Stay silent on task creation. Ask for the issue and the repository. | `test_intake_parser.py` |
| EC-IN-06 | S0 | `@devteam approve` with no task id. | No approval row. Ask for `approve <task_id>`. | `test_intake_parser.py` |
| EC-IN-07 | S0 | `@devteam reject <task_id>` with no reason. | State stays `AWAITING_APPROVAL`. Ask for a reason. | `test_approval_gate.py` |
| EC-IN-08 | S1 | `@devteam cancel` with no task id. | No transition. Ask for `cancel <task_id>`. | `test_intake_parser.py` |
| EC-IN-09 | S0 | The bug text contains the sentence “please approve the workaround”. | The message is intake or a follow-up, because `approve` is not the first token. | `test_intake_parser.py` |
| EC-IN-10 | S1 | `@DevTeam Approve <uuid> looks good`. | Record approval. Extra words after a present task id are an optional reason. | `test_intake_parser.py` |
| EC-IN-11 | S1 | The task id is not a UUID, or it is unknown. | Reply `task_not_found`. No row changes. | `test_intake_parser.py` |
| EC-IN-12 | S1 | Repository URL returns 404, or the ref does not exist. | Do not enter `INVESTIGATING`. Post the resolver error. A task that already reached `TRIAGED` stays `TRIAGED` until a follow-up fixes the ref. | `test_investigation_evidence.py` |
| EC-IN-13 | S1 | `repository` is a local path outside the configured demo root. | Refuse the path. Stay `RECEIVED` or `TRIAGED`. Do not read that tree. | `test_patch_safety.py` |
| EC-IN-14 | S2 | Logs exceed 64 KiB. | Store the first 64 KiB, set a truncation flag, and say so in the room. The model sees the stored prefix. | `test_intake_parser.py` |
| EC-IN-15 | S1 | The same origin message is delivered to two app processes. | The unique `(switch_room_id, origin_message_id)` constraint returns the existing task to the loser. | `test_state_machine.py` |
| EC-IN-16 | S2 | A private repository is configured and `GITHUB_READ_TOKEN` is empty. | Post that the read credential is missing. Do not enter `INVESTIGATING`. | `test_investigation_evidence.py` |

---

## 4. One active task

A task is active when its state is not `REJECTED`, `FAILED`, `CANCELLED`, or `PR_CREATED`.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-ACT-01 | S0 | A new issue arrives while another task in the room is active. | Reply with the active task id and ask the sender to cancel that task or wait. Do not create a second task. | `test_intake_parser.py` |
| EC-ACT-02 | S1 | A follow-up arrives while the active task is `INVESTIGATING` and waiting on evidence. | Attach the text to that task and run investigation once more. | `test_investigation_evidence.py` |
| EC-ACT-03 | S1 | `cancel <active_task_id>` arrives during `VALIDATING`. | Kill the sandbox, store the run as `error`, transition to `CANCELLED`. Do not move to `AWAITING_APPROVAL`. | `test_validation_capture.py` |
| EC-ACT-04 | S0 | `cancel <task_id>` arrives in `APPROVED`. | The state machine rejects the transition. Delivery continues or fails on its own. The approval row stays. | `test_state_machine.py` |
| EC-ACT-05 | S1 | A command names a terminal task while a different task is active. | Refuse that command. Leave both rows unchanged. | `test_state_machine.py` |
| EC-ACT-06 | S2 | The active task is `AWAITING_APPROVAL` and someone pastes a new bug. | Treat EC-ACT-01. The waiting proposal stays in `AWAITING_APPROVAL`. | `test_intake_parser.py` |

---

## 5. State machine

Legal edges are only those in the architecture’s `ALLOWED` map. `transition()` compares the current state and writes the event in one transaction.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-SM-01 | S0 | Caller requests `RECEIVED` → `PR_CREATED`. | `invalid_transition`. State and event log stay unchanged. | `test_state_machine.py` |
| EC-SM-02 | S0 | Caller requests `AWAITING_APPROVAL` → `PR_CREATED`. | `invalid_transition`. GitHub client is not constructed by this call. | `test_state_machine.py` |
| EC-SM-03 | S0 | Caller requests `PATCH_PROPOSED` → `APPROVED`. | `invalid_transition`. No approval row. | `test_state_machine.py` |
| EC-SM-04 | S0 | A second decision arrives after `APPROVED` or `REJECTED`. | The unique approval row is unchanged. The second call returns an error. | `test_approval_gate.py` |
| EC-SM-05 | S0 | Approve and cancel for the same task commit together. | One transaction wins. The loser receives `invalid_transition`. The row ends in exactly one of `APPROVED` or `CANCELLED`. | `test_state_machine.py` |
| EC-SM-06 | S1 | A stage calls `transition()` twice with the same target. | The second call fails. One event exists for that edge. | `test_state_machine.py` |
| EC-SM-07 | S1 | Any non-terminal state hits its timeout or retry limit. | Move to `FAILED`. The event payload holds the stage name and error. The room receives that payload. | `test_state_machine.py` |
| EC-SM-08 | S1 | `REJECTED`, `FAILED`, `CANCELLED`, or `PR_CREATED` receives a further stage call. | No outbound transition. | `test_state_machine.py` |
| EC-SM-09 | S0 | Delivery is invoked when the approval row’s `task_id` differs from the requested task. | `approval_required`. State unchanged. | `test_approval_gate.py` |
| EC-SM-10 | S1 | An invalid transition is attempted from the room. | The listener posts a short refusal. The refusal is an application log line, not a `workflow_event` that changes state. | `test_state_machine.py` |

---

## 6. Reasoning provider

Each task may complete `classify`, `hypothesize`, and `propose_patch` once, with one extra attempt only when the failure is a network error.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-LLM-01 | S1 | The provider times out at 60 seconds. | One retry with jitter. A second timeout moves the task to `FAILED`. | `test_reasoning_bounds.py` |
| EC-LLM-02 | S0 | The response is not the Pydantic model for that call. | Do not retry. `FAILED` with reason `invalid_model_output`. No partial classification is stored as final. | `test_reasoning_bounds.py` |
| EC-LLM-03 | S1 | `priority` is outside `critical`, `high`, `medium`, `low`. | Schema failure. Same outcome as EC-LLM-02. | `test_reasoning_bounds.py` |
| EC-LLM-04 | S1 | `summary`, `hypothesis`, or `diff` is empty. | Schema or patch-validator failure. The empty artifact is not posted as a result. | `test_reasoning_bounds.py` |
| EC-LLM-05 | S1 | HTTP 429 or 500. | One retry. Then `FAILED`. | `test_reasoning_bounds.py` |
| EC-LLM-06 | S1 | `REASONING_API_KEY` is empty. | `FAILED` before a stage pretends to classify. The room says the reasoning provider is not configured. | `test_reasoning_bounds.py` |
| EC-LLM-07 | S0 | The model returns a tool-like request to open a pull request or to mark tests passed. | The service drops unknown fields. State changes only through the stage method that was called. | `test_reasoning_bounds.py` |
| EC-LLM-08 | S1 | The same stage is entered twice because the room post was retried. | The second entry sees the stored artifact and returns it. The provider is not called again. | `test_reasoning_bounds.py` |

---

## 7. Investigation and evidence

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-INV-01 | S0 | Search returns no files. | Post the uncertainty. Stay `INVESTIGATING`. Do not call `propose_patch`. | `test_investigation_evidence.py` |
| EC-INV-02 | S0 | The hypothesis cites a path that was not in the retrieval set. | Drop that citation. Record it in `uncertainties`. | `test_investigation_evidence.py` |
| EC-INV-03 | S0 | Every citation is dropped. | Stay `INVESTIGATING`. Do not enter `PATCH_PROPOSED`. | `test_investigation_evidence.py` |
| EC-INV-04 | S1 | More than 8 files match. | Read 8. The finding states that the search was capped. | `test_investigation_evidence.py` |
| EC-INV-05 | S1 | A match is a binary file or a symlink whose target leaves the checkout. | Skip that path. Do not put those bytes in the prompt or the evidence table. | `test_investigation_evidence.py` |
| EC-INV-06 | S2 | The matching line sits in a very large file. | Store a window around the match, with real start and end lines. The excerpt equals those lines in the file at the pinned SHA. | `test_investigation_evidence.py` |
| EC-INV-07 | S0 | The branch moves after `resolve`. | Later reads, the sandbox, and the pull request stay on the pinned SHA. | `test_investigation_evidence.py` |
| EC-INV-08 | S1 | The checkout is empty, or the pinned tree has no files. | Post that evidence is missing. Stay `INVESTIGATING`. | `test_investigation_evidence.py` |
| EC-INV-09 | S1 | A stack frame names a file that is not in the tree. | Search the symbol. If it is still absent, record the missing path as an uncertainty. | `test_investigation_evidence.py` |
| EC-INV-10 | S0 | The room quote for a finding does not match `finding_evidence.excerpt`. | The post is rendered from the stored excerpt. The service does not let the model rewrite the quote after the row is saved. | `test_investigation_evidence.py` |

---

## 8. Patch safety

A diff is stored only when it is a unified diff, at most 400 lines, non-empty, and every path stays inside the checkout. `git apply --check` must succeed with no fuzz before `VALIDATING`.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-PAT-01 | S0 | A path is absolute or contains `..`. | Reject the diff. `FAILED` with reason `unsafe_diff`. Nothing is applied. | `test_patch_safety.py` |
| EC-PAT-02 | S0 | The diff is empty or is prose with no hunks. | `FAILED` with reason `invalid_diff`. | `test_patch_safety.py` |
| EC-PAT-03 | S1 | The diff is longer than 400 lines. | `FAILED` with reason `diff_too_large`. | `test_patch_safety.py` |
| EC-PAT-04 | S0 | The diff creates a symlink, a submodule, or a binary delta. | `FAILED` with reason `unsafe_diff`. | `test_patch_safety.py` |
| EC-PAT-05 | S0 | `git apply --check` fails, including a whitespace or line-ending mismatch. | `FAILED`. The event payload and the room contain the apply output. State does not become `AWAITING_APPROVAL`. | `test_patch_safety.py` |
| EC-PAT-06 | S0 | The diff applies only with fuzz or an offset. | Treat that as a failed apply. Do not change nearby lines. | `test_patch_safety.py` |
| EC-PAT-07 | S1 | The diff adds a file under the repo root that was not in the retrieval set, such as a new test. | Allow it when the path checks and `git apply --check` pass. | `test_patch_safety.py` |
| EC-PAT-08 | S1 | The diff deletes or empties a file under `tests/`. | Continue to validation. The room message lists those paths under risks. | `test_patch_safety.py` |
| EC-PAT-09 | S0 | Two diffs are wrapped in one model response. | Accept one fenced unified diff. Zero or several candidates is `invalid_diff`. | `test_patch_safety.py` |
| EC-PAT-10 | S1 | A second patch arrives for a task that already has one. | The MVP keeps a single patch row. A replacement is refused. A new attempt is a new task. | `test_patch_safety.py` |

---

## 9. Sandbox and test evidence

The sandbox is a fresh directory at the pinned SHA, then a short-lived container: network `none`, 512 MB, 1 CPU, non-root, 120 second timeout, workspace as the only writable mount. Pytest’s argv is built by the service. Recommended test paths are arguments, not a shell line.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-VAL-01 | S0 | Pytest exits 0. | `status = passed`, state `AWAITING_APPROVAL`, room text quotes stored stdout and stderr. | `test_validation_capture.py` |
| EC-VAL-02 | S0 | Pytest exits non-zero, including exit 5 when no tests are collected. | `status = failed`, state `AWAITING_APPROVAL`. The non-zero code is visible. The summary still says the suite failed. | `test_validation_capture.py` |
| EC-VAL-03 | S0 | The container is killed, the image is missing, or Docker returns before the process starts. | `status = error`, `exit_code` null, state `FAILED`. | `test_validation_capture.py` |
| EC-VAL-04 | S0 | The run exceeds 120 seconds. | Kill the container. Same outcome as EC-VAL-03, reason `timeout`. | `test_validation_capture.py` |
| EC-VAL-05 | S1 | The container hits the memory limit. | `status = error`, state `FAILED`, reason `oom`. | `test_validation_capture.py` |
| EC-VAL-06 | S0 | A recommended test path contains a shell metacharacter, a newline, or a dash-dash argument. | Drop the recommendation and run `pytest -q`. Record that substitution in `risks`. | `test_validation_capture.py` |
| EC-VAL-07 | S1 | Pytest passes and the optional Ruff command fails. | Two `validation_run` rows. The pytest row decides `passed`. Risks include the Ruff output. State becomes `AWAITING_APPROVAL`. | `test_validation_capture.py` |
| EC-VAL-08 | S0 | Stdout or stderr contains a configured token value. | Persist and post the streams with those values redacted. The exit code stays exact. | `test_validation_capture.py` |
| EC-VAL-09 | S2 | Combined output exceeds 200 KiB. | Store the head and tail, mark truncation, and keep the exact exit code. | `test_validation_capture.py` |
| EC-VAL-10 | S0 | Tests change files inside the sandbox after apply. | Delivery commits the stored diff onto a clean tree at the pinned SHA. Sandbox edits are discarded with the container. | `test_validation_capture.py` |
| EC-VAL-11 | S0 | The process restarts after apply and before an exit code is stored. | On startup: `status = error`, state `FAILED`, reason `interrupted`. | `test_validation_capture.py` |
| EC-VAL-12 | S1 | The suite tries to open a network connection. | The container has no network. The resulting pytest output is stored as EC-VAL-02 or EC-VAL-04. The service does not rerun the suite with network enabled. | `test_validation_capture.py` |
| EC-VAL-13 | S1 | Two validations for one task overlap. | The per-task lock allows one sandbox. The second waits or is refused while the first holds the lock. | `test_validation_capture.py` |

---

## 10. Approval

`decide` requires state `AWAITING_APPROVAL`, a human reviewer id different from the agent id, and membership in the task’s room.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-AP-01 | S0 | Reviewer id is missing. | No approval row. Error returned to the listener. | `test_approval_gate.py` |
| EC-AP-02 | S0 | Reviewer id equals the agent id. | No approval row, including when the display name looks human. | `test_approval_gate.py` |
| EC-AP-03 | S0 | The sender is not a human member of the room. | No approval row. Another agent in the room cannot approve. | `test_approval_gate.py` |
| EC-AP-04 | S0 | The display name matches a human and the sender id does not. | Identity is the sender id from the Switch event. The decision is refused when that id fails EC-AP-02 or EC-AP-03. | `test_approval_gate.py` |
| EC-AP-05 | S0 | State is `INVESTIGATING`, `VALIDATING`, `RECEIVED`, or `PATCH_PROPOSED`. | `invalid_transition`. No approval row. | `test_approval_gate.py` |
| EC-AP-06 | S0 | Two humans approve the same task at once. | One `approval` row. One of the calls receives a uniqueness or transition error. | `test_approval_gate.py` |
| EC-AP-07 | S1 | The decision message is replayed after a successful approve. | Dedup on `message_id` performs no second write. | `test_approval_gate.py` |
| EC-AP-08 | S0 | A dashboard client calls the API with `DASHBOARD_TOKEN`. | The token can read tasks. The API has no approve, reject, intake, or pull-request route. | `test_api_dashboard.py` |
| EC-AP-09 | S1 | `reject <task_id>` includes a reason and the sender is valid. | One approval row with `decision = rejected`. State `REJECTED`. Delivery is not started. | `test_approval_gate.py` |
| EC-AP-10 | S2 | The reviewer approves with a reason. | Store the optional reason. State `APPROVED`. | `test_approval_gate.py` |

---

## 11. Delivery

`create_pull_request` loads the task, the approval, the patch, the findings, and the validation runs. It calls GitHub only when `state` is `APPROVED` and `approval.decision` is `approved`.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-DL-01 | S0 | Delivery is called in `AWAITING_APPROVAL`. | `approval_required` before any GitHub write. The remote has no new branch from this call. | `test_approval_gate.py` |
| EC-DL-02 | S0 | Delivery is called in `REJECTED`, `FAILED`, or `CANCELLED`. | `approval_required`. No write. | `test_approval_gate.py` |
| EC-DL-03 | S0 | The approval row was written with the agent id. | The row cannot be created (EC-AP-02). A hand-inserted row still fails the delivery actor check. | `test_approval_gate.py` |
| EC-DL-04 | S1 | `GITHUB_DELIVERY_TOKEN` is empty. | Remain `APPROVED`. Tell the room that pull-request creation is not configured. | `test_delivery.py` |
| EC-DL-05 | S1 | GitHub returns 401 or 403. | One retry, then `FAILED`. The approval row remains. The room gets the error with the token redacted. | `test_delivery.py` |
| EC-DL-06 | S1 | The branch is created and the pull-request call then fails. | `FAILED` after one retry. The room names the branch `devteam/<task_id>` so the partial publish is visible. | `test_delivery.py` |
| EC-DL-07 | S0 | GitHub returns a URL and the process stops before `PR_CREATED` is committed. | On the next delivery attempt, look up that branch. If a pull request exists, store its URL and move to `PR_CREATED`. Do not open a second pull request. | `test_delivery.py` |
| EC-DL-08 | S1 | The base ref no longer exists on the remote. | `FAILED`. Approval remains. No force-push. | `test_delivery.py` |
| EC-DL-09 | S0 | The pull-request body is assembled. | Include the issue, evidence paths, change summary, the real command and exit code, a bounded output excerpt, and the reviewer id, name, and timestamp. | `test_delivery.py` |
| EC-DL-10 | S1 | Validation status is `failed` and the human still approved. | Delivery is allowed. The body shows the failing exit code. The service does not rewrite it as a pass. | `test_delivery.py` |
| EC-DL-11 | S0 | Delivery is asked to deploy or merge the pull request. | The client exposes pull-request creation only. The run ends at `PR_CREATED`. | `test_delivery.py` |

---

## 12. Restart and persistence

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-DB-01 | S0 | Restart while state is `AWAITING_APPROVAL`. | The task, patch, findings, and validation rows are still there. A later valid `approve <task_id>` works. Stages are not repeated. | `test_restart.py` |
| EC-DB-02 | S0 | Restart while state is `VALIDATING` and `exit_code` is null. | Startup recovery sets the run to `error` and the task to `FAILED` / `interrupted`. | `test_restart.py` |
| EC-DB-03 | S1 | Restart while state is `TRIAGED`, `INVESTIGATING`, or `PATCH_PROPOSED`. | Leave the state as stored. Post it once. Wait for a follow-up before any new provider call. | `test_restart.py` |
| EC-DB-04 | S1 | Restart while state is `APPROVED` and no pull-request row exists. | Leave `APPROVED`. A delivery retry is an explicit follow-up `approve` replay or an operator rerun of delivery for that task id. It still passes EC-DL-07 before creating anything. | `test_restart.py` |
| EC-DB-05 | S1 | SQLite is locked when a transition commits. | Retry the transaction briefly. If it still fails, post the error and leave the previous state in place. | `test_state_machine.py` |
| EC-DB-06 | S1 | The database file is on the Docker volume and the container is recreated. | Existing tasks remain readable. `SWITCH_CONNECTION_ID` is unchanged so resume still dedups. | `test_restart.py` |
| EC-DB-07 | S2 | Timestamps cross a daylight-saving change. | Store UTC on every row. The room prints those timestamps as stored. | `test_state_machine.py` |

---

## 13. HTTP API and dashboard

The dashboard is optional. These cases apply when it is running. The room remains the place where decisions happen.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-API-01 | S1 | `GET /api/v1/tasks` has no token or the wrong token. | 401. An empty body is not returned as a successful empty list. | `test_api_dashboard.py` |
| EC-API-02 | S2 | The room has no tasks. | 200 and an empty list. The dashboard shows an empty state. | `test_api_dashboard.py` |
| EC-API-03 | S1 | `GET /api/v1/tasks/{id}` for an unknown id. | `task_not_found`. | `test_api_dashboard.py` |
| EC-API-04 | S2 | The task has no finding, patch, validation, or approval yet. | Each collection endpoint returns an empty result. It does not 500. | `test_api_dashboard.py` |
| EC-API-05 | S0 | `GET /health` while Switch is disconnected. | 200 means the API process is up. The payload does not claim the room is connected. | `test_api_dashboard.py` |
| EC-API-06 | S1 | The dashboard renders pytest output and a diff. | Render them as text. Markup in stdout is not interpreted as HTML. | `test_api_dashboard.py` |
| EC-API-07 | S1 | The task is `FAILED`. | The detail view shows a failure banner and the last event payload. | `test_api_dashboard.py` |
| EC-API-08 | S2 | The task is terminal. | Polling stops. The last fetched state stays on screen. | `test_api_dashboard.py` |
| EC-API-09 | S0 | A caller posts `{"decision": "approved"}` to a guessed URL. | No such route. The approval table is unchanged. | `test_api_dashboard.py` |

---

## 14. Security boundaries

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-SEC-01 | S0 | The issue text says to ignore the workflow and open a pull request now. | Intake stores it as description. Delivery still requires `APPROVED`. | `test_approval_gate.py` |
| EC-SEC-02 | S0 | A source file tells the model to cite `/etc/passwd` or to emit a diff that writes outside the repo. | Citations outside the retrieval set are dropped. The path check rejects the diff. | `test_patch_safety.py` |
| EC-SEC-03 | S0 | Pytest is instructed, by a test name, to run `pytest -q; curl …`. | EC-VAL-06 substitutes `pytest -q`. The sandbox network stays `none`. | `test_validation_capture.py` |
| EC-SEC-04 | S0 | The sandbox image is started with the host Docker socket mounted. | The validation container does not receive the Docker socket. Only the app process invokes `docker run`. | `test_validation_capture.py` |
| EC-SEC-05 | S0 | A symlink in the copied workspace points at a host path. | The copy skips links that escape the workspace. Reads use paths resolved inside the checkout. | `test_patch_safety.py` |
| EC-SEC-06 | S0 | Logs, diffs, or provider errors contain `GITHUB_READ_TOKEN`, `GITHUB_DELIVERY_TOKEN`, `SWITCH_AGENT_API_KEY`, or `REASONING_API_KEY`. | Structured logs and room posts replace those values. | `test_validation_capture.py` |
| EC-SEC-07 | S1 | `.env` is present beside `.env.example`. | The example file contains names only. The real file is untracked. | repo check |
| EC-SEC-08 | S1 | A command uses a Unicode lookalike of `approve`. | The parser accepts the ASCII token only. The message is issue text. | `test_intake_parser.py` |

---

## 15. Demonstration scenario

Use case: the checkout API returns HTTP 500 after login. The demo repo’s handler assumes a session field that login never sets. A regression test fails on the pinned tree and passes after a correct minimal patch.

| ID | Severity | Condition | Required outcome | Test |
|---|---|---|---|---|
| EC-DEMO-01 | S0 | The agent prompt or room instructions include the root cause or the patch. | The reasoning calls receive the issue text and retrieved excerpts only. | demo review |
| EC-DEMO-02 | S0 | Investigation cannot read the checkout and login modules. | The finding quotes stored lines from those files, or it stays `INVESTIGATING` under EC-INV-03. | `test_investigation_evidence.py` |
| EC-DEMO-03 | S0 | The suite is executed on the unpatched tree by mistake. | The sandbox applies the stored diff before pytest. A run without a successful apply is `FAILED`, not a pass. | `test_validation_capture.py` |
| EC-DEMO-04 | S0 | The proposed fix is wrong and pytest still fails. | EC-VAL-02. The human can reject. No pull request is opened. | `test_validation_capture.py` |
| EC-DEMO-05 | S0 | Someone calls delivery before `approve <task_id>`. | EC-DL-01. The recording can show this refusal. | `test_approval_gate.py` |
| EC-DEMO-06 | S1 | The reviewer rejects a good patch. | State `REJECTED`. A later attempt is a new task. The rejected diff is not reused silently. | `test_approval_gate.py` |
| EC-DEMO-07 | S1 | Switch or Mattermost is down when the demo starts. | The app logs the connection failure. The runbook starts Switch before the issue is posted. No local chat substitute posts the result. | runbook |

---

## 16. Cases the MVP leaves alone

These inputs can appear in a real team. The MVP’s response is the behavior in the last column, which keeps one room and one agent honest.

| Situation | MVP behavior |
|---|---|
| A second chat product sends the same issue. | Ignored. People use the Switch room that is already bridged to Mattermost. |
| Two issues should run in parallel. | EC-ACT-01. Cancel or wait. |
| The reviewer wants a revised diff after `REJECTED`. | The terminal task stays rejected. A new addressed issue starts a new task. |
| The team wants the pull request merged and deployed. | The system stops at `PR_CREATED`. |
| More than one Switch agent shares the work. | Optional later. This state machine remains the only writer of approval and delivery. |
| Kubernetes, several tenants, or a trained model. | Outside the product. |

---

## 17. Test map

| Test module | Cases |
|---|---|
| `backend/tests/test_state_machine.py` | EC-IN-15, EC-ACT-04, EC-ACT-05, EC-SM-01 through EC-SM-08, EC-SM-10, EC-DB-05, EC-DB-07 |
| `backend/tests/test_approval_gate.py` | EC-SW-12, EC-SW-13, EC-IN-07, EC-SM-04, EC-SM-09, EC-AP-01 through EC-AP-10, EC-DL-01 through EC-DL-03, EC-SEC-01, EC-DEMO-05, EC-DEMO-06 |
| `backend/tests/test_patch_safety.py` | EC-IN-13, EC-PAT-01 through EC-PAT-10, EC-SEC-02, EC-SEC-05 |
| `backend/tests/test_validation_capture.py` | EC-ACT-03, EC-VAL-01 through EC-VAL-13, EC-SEC-03, EC-SEC-04, EC-SEC-06, EC-DEMO-03, EC-DEMO-04 |
| `backend/tests/test_intake_parser.py` | EC-SW-10, EC-SW-11, EC-IN-01 through EC-IN-11, EC-IN-14, EC-ACT-01, EC-ACT-06, EC-SEC-08 |
| `backend/tests/test_listener_filter.py` | EC-SW-03, EC-SW-04 |
| `backend/tests/test_listener_resume.py` | EC-SW-01, EC-SW-02, EC-SW-05 through EC-SW-09 |
| `backend/tests/test_reasoning_bounds.py` | EC-LLM-01 through EC-LLM-08 |
| `backend/tests/test_investigation_evidence.py` | EC-IN-12, EC-IN-16, EC-ACT-02, EC-INV-01 through EC-INV-10, EC-DEMO-02 |
| `backend/tests/test_delivery.py` | EC-DL-04 through EC-DL-11 |
| `backend/tests/test_restart.py` | EC-DB-01 through EC-DB-04, EC-DB-06 |
| `backend/tests/test_api_dashboard.py` | EC-AP-08, EC-API-01 through EC-API-09 |

S0 cases in `test_approval_gate.py`, `test_patch_safety.py`, `test_validation_capture.py`, and `test_state_machine.py` belong in the mandatory pytest run. Listener, delivery, restart, and dashboard tests follow the same assertions and may use fakes for Switch, GitHub, and Docker.

---

**Product principle:** Collaborative AI, evidence-driven engineering, and human-controlled execution.
