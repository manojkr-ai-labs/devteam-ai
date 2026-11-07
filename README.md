# DevTeam

## What the room does

One Switch room socket handles addressed messages. The listener acts only when `payload.addressed` is true. It ignores this agent's own posts, deduplicates `(room_id, message_id)`, and replies to every ping with a pong that includes the cursor. After a drop, it reconnects with the same connection id and `start_from`. Events at or below the stored cursor are ignored.

Commands go to a decider. Issues go to intake. The task id is posted when intake commits. Stages after intake run as background tasks under a per-task lock so the socket keeps answering pings.

The DevTeam Dossier and GitHub pull-request creation are not in this submission. This submission states no timing or fix-rate claim. Pytest was not run in the recorded room. A room approval is not part of this submission unless the video shows it.

## Install the backend

From the repository root, create a virtual environment and install the backend:

```bash
python -m venv backend/.venv
```

Windows:

```bash
backend\.venv\Scripts\python -m pip install -e backend
```

macOS and Linux:

```bash
backend/.venv/bin/python -m pip install -e backend
```

## Run pytest

From the repository root, with that environment:

Windows:

```bash
backend\.venv\Scripts\python -m pytest backend
```

macOS and Linux:

```bash
backend/.venv/bin/python -m pytest backend
```

## Switch and Mattermost

Switch and Mattermost are started with the documented Switch Console or Switch server flow from the Switch docs. This repository does not start them. Set `SWITCH_BASE_URL` to that server.

## Start the agent

Copy `.env.example` to `.env` in the repository root and set the values. `SWITCH_CONNECTION_ID` is a UUID. `CHECKOUT_PATH` is an existing local directory. From the repository root:

```bash
backend\.venv\Scripts\python -m app.main
```

## Issue message to post

Post this addressed issue in the configured Switch room:

```text
@devteam investigate
Repo: .
Ref: main

Checkout API returns HTTP 500 after user login.
```

`Repo: .` means `CHECKOUT_PATH`. The agent does not clone a GitHub URL. When intake commits, the room posts the task id.
