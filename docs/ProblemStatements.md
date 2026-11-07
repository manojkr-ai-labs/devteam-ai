# DevTeam AI

## Collaborative Software Incident Resolution Platform

| | |
|---|---|
| **Hackathon** | Flip the Switch 2026 |
| **Organizer** | WeMakeDevs |
| **Primary Track** | Best Business Workflow |
| **Project Type** | AI Engineering Collaboration |
| **Version** | 4.0 |
| **Status** | Final MVP Specification |

This document is the canonical project context for DevTeam AI. It defines the problem, users, solution, requirements, workflow, architecture, scope, risks, acceptance criteria, and demonstration plan.

---

## Contents

1. [Problem Definition](#1-problem-definition)
2. [Target Users and Business Value](#2-target-users-and-business-value)
3. [Proposed Solution](#3-proposed-solution)
4. [Product Differentiation](#4-product-differentiation)
5. [Core Functional Requirements](#5-core-functional-requirements)
6. [Engineering Workflow](#6-engineering-workflow)
7. [Agent Responsibilities](#7-agent-responsibilities)
8. [Technical Architecture](#8-technical-architecture)
9. [Workflow State Management](#9-workflow-state-management)
10. [Non-Functional Requirements](#10-non-functional-requirements)
11. [Technology Stack](#11-technology-stack)
12. [MVP Scope](#12-mvp-scope)
13. [Security and Risk Controls](#13-security-and-risk-controls)
14. [Acceptance Criteria](#14-acceptance-criteria)
15. [Evaluation Metrics](#15-evaluation-metrics)
16. [Demonstration Scenario](#16-demonstration-scenario)
17. [Submission Deliverables](#17-submission-deliverables)
18. [Final Objective](#18-final-objective)

---

## 1. Problem Definition

Software engineering teams spend considerable time investigating bugs, identifying root causes, preparing code fixes, validating changes, and coordinating reviews.

AI coding assistants can generate code and answer technical questions, but individual developer interactions do not necessarily provide a structured workflow for team-wide engineering collaboration.

The missing capability is a shared, traceable process connecting human developers, AI-assisted investigation, code changes, automated validation, and engineering approval.

DevTeam AI addresses this problem by introducing an AI engineering teammate that collaborates with developers through Switch.

---

## 2. Target Users and Business Value

### Primary users

- Software developers
- Full-stack engineers
- Engineering managers
- QA engineers

### Business value

- Reduce repetitive issue-investigation activities.
- Improve the consistency of technical findings.
- Accelerate preparation of code fixes.
- Make test results available during code review.
- Maintain accountability for AI-generated changes.

Product effectiveness will be evaluated using actual execution data rather than assumed productivity improvements.

---

## 3. Proposed Solution

DevTeam AI converts developer-reported software issues into evidence-backed, testable, and human-approved engineering changes.

A developer reports an issue in a Switch collaboration room. The AI engineering teammate investigates the repository, proposes a minimal code modification, executes relevant tests, and communicates the results through the shared room.

The developer reviews the proposed changes and explicitly authorizes delivery.

### Core workflow

```text
Developer Issue → Switch → AI Investigation → Code Proposal → Automated Validation → Human Approval → GitHub Pull Request
```

Switch is the central collaboration layer through which humans and AI agents exchange tasks, findings, decisions, and progress updates.

---

## 4. Product Differentiation

DevTeam AI is a collaborative engineering workflow, distinct from a generic AI chatbot or a standalone code generator.

Its differentiation is based on four capabilities:

1. **Collaborative execution:** Human developers and AI agents work through a shared Switch environment.
2. **Evidence-based investigation:** Technical findings reference actual repository files and code.
3. **Verifiable engineering:** Proposed changes are validated through real test execution.
4. **Human-controlled delivery:** External code changes require explicit human authorization.

---

## 5. Core Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Connect an AI engineering agent through Switch | P0 |
| FR-02 | Receive engineering requests through a Switch room | P0 |
| FR-03 | Classify and prioritize reported issues | P0 |
| FR-04 | Investigate repository source code | P0 |
| FR-05 | Identify relevant files and potential root causes | P0 |
| FR-06 | Generate reviewable code patches | P0 |
| FR-07 | Execute relevant automated tests | P0 |
| FR-08 | Capture actual execution evidence | P0 |
| FR-09 | Present findings through Switch | P0 |
| FR-10 | Enforce explicit human approval | P0 |
| FR-11 | Maintain task and execution history | P1 |
| FR-12 | Create GitHub pull requests after approval | P1 |
| FR-13 | Display workflow status in a dashboard | P1 |

- **P0:** Required for the core MVP.
- **P1:** Additional functionality where time permits.

---

## 6. Engineering Workflow

### Step 1: Issue Intake

**Input**

- Engineering issue description.
- Repository reference.
- Relevant error messages or logs.

**Expected result**

- Unique task identifier.
- Structured issue description.
- Initial priority.

### Step 2: Issue Investigation

The investigation process must:

- Inspect relevant repository files.
- Identify related functions and dependencies.
- Produce a root-cause hypothesis.
- Reference supporting source files.
- Identify uncertainties and missing evidence.

**Expected result**

- Investigation summary.
- Relevant file paths.
- Evidence-backed findings.
- Recommended corrective action.

### Step 3: Code Proposal

The engineering agent must:

- Generate minimal code changes.
- Explain the proposed modification.
- Identify affected files.
- Suggest regression tests.
- Prepare a reviewable patch.

**Expected result**

- Proposed patch.
- Change summary.
- Test recommendations.

### Step 4: Automated Validation

The validation process must:

- Execute relevant tests.
- Run configured quality checks.
- Capture actual command output.
- Identify failures and warnings.
- Report validation status.

**Expected result**

- Test execution report.
- Actual test results.
- Remaining risks.

### Step 5: Human Approval

The system must:

- Present the patch and evidence.
- Allow approval or rejection.
- Record reviewer identity and timestamp.
- Reject unauthorized delivery attempts.

### Step 6: Code Delivery

Following explicit approval:

- Prepare a GitHub pull request.
- Include the issue summary.
- Reference the proposed changes.
- Include available test evidence.
- Return the pull-request URL through Switch.

---

## 7. Agent Responsibilities

The MVP uses one primary Switch-connected coding agent. Its responsibilities are logically separated to maintain clarity and allow future specialization.

| Responsibility | Expected output |
|---|---|
| Triage | Classification, priority, and task summary |
| Investigation | Root-cause hypothesis and source evidence |
| Engineering | Proposed patch and change summary |
| QA | Actual test results and validation status |
| Human reviewer | Approval or rejection decision |

Additional independent agents are optional and must not compromise the working end-to-end workflow.

---

## 8. Technical Architecture

### Collaboration Layer

- Switch
- Mattermost
- Human developers
- Switch-connected AI agent

### Application Layer

- Python
- FastAPI
- Pydantic
- Task management
- Workflow orchestration

### Engineering Layer

- Repository access
- Code investigation
- Patch generation
- Isolated test execution
- Validation reporting

### Persistence Layer

- SQLite for initial task storage
- Execution history
- Approval records
- Patch references

### Delivery Layer

- GitHub API
- Human approval
- Pull-request creation
- Execution audit trail

### Frontend

- Next.js
- TypeScript
- Tailwind CSS

The application must use documented Switch integration capabilities. A custom collaboration implementation must not replace Switch.

---

## 9. Workflow State Management

### Supported states

```text
RECEIVED
TRIAGED
INVESTIGATING
PATCH_PROPOSED
VALIDATING
AWAITING_APPROVAL
APPROVED
PR_CREATED
```

### Failure and alternative states

```text
REJECTED
FAILED
CANCELLED
```

### Requirements

- Validate state transitions.
- Persist important workflow events.
- Record timestamps and responsible actors.
- Reject invalid transitions.
- Require explicit human authorization before pull-request creation.

---

## 10. Non-Functional Requirements

### Reliability

- Bounded agent execution.
- Error handling and retry limits.
- Persistent task history.
- Clear failure reporting.

### Security

- Environment-based secrets management.
- Restricted repository permissions.
- Isolated execution of untrusted code.
- Server-side approval verification.
- No automatic production deployment.

### Maintainability

- Modular application structure.
- Typed contracts.
- Separation of business logic and infrastructure.
- Automated testing.
- Structured logging.

### Performance

- Minimize unnecessary LLM calls.
- Limit execution time.
- Avoid redundant agent operations.
- Keep the MVP lightweight.

---

## 11. Technology Stack

| Component | Technology |
|---|---|
| Collaboration | Switch |
| Communication | Mattermost |
| AI development | Cursor Pro |
| Backend | Python, FastAPI |
| Contracts | Pydantic |
| Frontend | Next.js, TypeScript |
| UI styling | Tailwind CSS |
| Persistence | SQLite |
| Repository integration | GitHub API |
| Testing | Pytest |
| Code quality | Ruff, Mypy |
| Containerization | Docker |

---

## 12. MVP Scope

### Mandatory

- Working Switch integration.
- Real human-agent communication.
- Engineering issue intake.
- Repository investigation.
- Evidence-backed findings.
- Code-fix proposal.
- Actual automated test execution.
- Human approval.
- Reproducible demonstration.

### Optional

- GitHub pull-request automation.
- Next.js dashboard.
- Detailed execution analytics.
- Multiple independent agents.

### Out of Scope

- Kubernetes deployment.
- Foundation-model training.
- Multi-tenant enterprise infrastructure.
- Autonomous production deployment.
- Multiple communication platform integrations.

---

## 13. Security and Risk Controls

| Risk | Required control |
|---|---|
| Incorrect code proposals | Human review and tests |
| Untrusted repository code | Isolated execution |
| Credential exposure | Scoped credentials and environment configuration |
| Agent execution failure | Timeouts and error handling |
| Unauthorized code delivery | Server-side approval enforcement |
| Incorrect test reporting | Capture real command output |
| Invalid workflow transitions | State-machine validation |

---

## 14. Acceptance Criteria

The MVP must demonstrate all of the following:

1. A developer communicates with an AI agent through Switch.
2. An engineering issue is successfully received.
3. The issue is classified and investigated.
4. Relevant repository files are identified.
5. Findings include supporting evidence.
6. A proposed code modification is generated.
7. Automated tests execute and produce actual results.
8. The human reviewer can approve or reject the proposal.
9. Unauthorized pull-request creation is prevented.
10. Workflow execution is traceable and reproducible.

---

## 15. Evaluation Metrics

The following measurements will be collected during the demonstration:

| Metric | Measurement |
|---|---|
| Switch integration | Successful human-agent interactions |
| Investigation quality | Findings supported by source evidence |
| Code proposal quality | Reviewability of generated changes |
| Test execution | Actual test results |
| Approval enforcement | Unauthorized delivery attempts rejected |
| Traceability | Recorded task and agent events |
| Reproducibility | Successful execution using setup instructions |

No productivity gains or performance improvements will be claimed without measured results.

---

## 16. Demonstration Scenario

**Use case:** Checkout API returns HTTP 500 after user login.

Expected demonstration:

1. Developer reports the issue in a Switch room.
2. AI teammate acknowledges the request.
3. Issue is classified and prioritized.
4. Repository investigation identifies relevant source code.
5. The agent presents a root-cause hypothesis and evidence.
6. A minimal code fix is proposed.
7. Automated regression tests execute.
8. Actual results are presented through Switch.
9. Developer approves or rejects the patch.
10. An approved change is delivered through GitHub.

The demonstration must show genuine Switch communication and actual engineering execution.

---

## 17. Submission Deliverables

- Source code repository.
- Working Switch integration.
- `README.md`.
- `ProblemStatements.txt`.
- Architecture documentation.
- Environment configuration example.
- Automated test evidence.
- Installation instructions.
- Demonstration video.

---

## 18. Final Objective

Build a reliable AI engineering teammate that collaborates with software developers through Switch to investigate real engineering issues, generate evidence-backed code proposals, validate changes, and support human-approved delivery.

**Product principle:** Collaborative AI, evidence-driven engineering, and human-controlled execution.
