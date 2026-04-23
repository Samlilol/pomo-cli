# PRD: Agent-Native Work Observability

**Product:** `pomo-cli`
**Status:** Canonical product definition
**Last updated:** 2026-04-23
**Supersedes:** `2026-04-22-VISION.md`

This document is the single source of truth for product scope, sequencing, and terminology. Sprint notes, experiments, skills, and implementation details are secondary. If they conflict with this PRD, this PRD wins.

---

## 1. Product Summary

`pomo-cli` is a local-first runtime for tracking agent-assisted work at the task level.

The product promise is:

- track work against a real task, not just an app window
- record total task time with truthful task/session history
- distinguish how time was spent across human work, agent execution, review, idle, and blocked states
- help close the loop with summaries and optional post-backs to external systems

One-line framing:

**An MCP-native work observability runtime for agent-assisted tasks.**

---

## 2. Problem

Knowledge work in the agent era is no longer well described by "hours spent in an app."

Current tools fail in three ways:

1. **Manual tracking fails.** Traditional timers require the user to remember to start and stop them.
2. **App analytics lack task semantics.** Tools like RescueTime know which app is open, not which ticket or deliverable is being worked on.
3. **Agent-era time is collapsed into one number.** Existing tools do not separate human-active time from agent execution, review time, or blocked time.

This creates bad retrospectives, bad capacity assumptions, and bad visibility into agent ROI.

---

## 3. Users and Jobs

### 3.1 Primary User

An individual developer or knowledge worker who:

- uses Claude Code, Codex, Cursor, Windsurf, or similar tools
- works against named tasks such as Linear tickets, GitHub issues, or explicit deliverables
- wants visibility into where time went
- will not tolerate heavy manual tracking overhead

### 3.2 Secondary User

An engineering lead or manager who wants:

- more truthful capacity data
- visibility into human time vs agent leverage
- task-level work patterns, not just ticket counts

### 3.3 Core Jobs To Be Done

When I work with an agent:

- I want the work associated with the correct task
- I want the system to preserve a truthful session history as work starts, pauses, resumes, and finishes
- I want to understand how much of the elapsed time was human work vs agent execution vs review vs idle
- I want task closeout to be easier, not another chore
- I want end-of-day review to reflect what actually happened

---

## 4. Product Principles

1. **Runtime first, orchestration second.**
   The product begins when a task/session exists. Skills, prompts, CLIs, and future integrations may decide when to call the runtime.

2. **Local-first by default.**
   Core tracking must work locally with no cloud dependency.

3. **Semantic task identity beats app-level metrics.**
   The unit of value is a task, ticket, or deliverable, not "time in VS Code."

4. **Time composition is the differentiator.**
   Simple wall-clock tracking is table stakes. The product becomes unique when it can explain how the time was spent.

5. **Closure matters.**
   A useful system does not stop at elapsed time. It helps summarize work and update the systems around the task.

6. **External side effects require confirmation.**
   The product may suggest updates to Linear, Slack, or Git, but should not make those writes silently.

7. **Graceful degradation over brittle magic.**
   If the classifier or integrations are uncertain, the system should still provide clean task/session tracking instead of failing entirely.

---

## 5. Product Definition

### 5.1 What The Product Is

The product has four layers:

- **Task/session runtime**
  Local primitives for creating, resuming, closing, completing, and summarizing work against semantic tasks.

- **Time classifier**
  The layer that splits elapsed time into meaningful categories such as `USER_ACTIVE`, `AGENT_EXECUTING`, `USER_REVIEWING`, `IDLE`, and `BLOCKED`.

- **Summary and closure layer**
  Generates per-task and per-day summaries, and proposes post-backs to external systems after confirmation.

- **Client and integration layer**
  Skills, MCP clients, CLIs, and future hooks or webhooks that call the runtime.

### 5.2 What Is Core vs Optional

**Core product primitives:**

- create a task session
- continue a task across multiple sessions
- close a session without marking the task done
- complete a task
- retrieve current task/session state
- retrieve daily and per-task summaries
- expose these primitives through both CLI and MCP

**Core differentiator:**

- classify time composition within a task

**Optional entry mechanisms:**

- explicit user commands
- skill-driven orchestration
- future auto-trigger or webhook-driven starts

Important product decision:

**Auto-trigger is not the product.** It is one possible client behavior. We do not need dedicated `auto-start` or `propose-complete` runtime commands in v1 unless a real cross-client requirement emerges that cannot be handled cleanly at the skill or client layer.

### 5.3 What The Product Is Not

- not a pomodoro app for disciplined manual timer users
- not a dashboard-first analytics tool
- not a project management replacement
- not a billing or invoicing system
- not surveillance software
- not a planning app first

Planning and backlog management may remain useful supporting features, but they are not the product thesis.

---

## 6. Current Product Baseline

### 6.1 What Exists In The Repo Today

The current codebase already provides:

- a local SQLite-backed task/session runtime
- CLI commands for `start`, `plan`, `run`, `continue`, `watch`, `status`, `complete`, `summary`, and `backlog`
- MCP tools for the same core task/session operations
- day-based task IDs
- session accumulation across the same task
- daily summary output

### 6.2 What Is Missing Relative To The Product

The current codebase does **not** yet provide:

- time composition classification
- durable end-of-task summary generation
- confirmed external post-backs to Linear, Slack, or Git
- a general signal-ingestion layer beyond explicit client behavior

The current implementation is therefore a good runtime foundation, but not yet the full product described here.

---

## 7. Core User Flows

### 7.1 Explicit Start

1. User identifies the task.
2. Client starts tracking against that semantic task.
3. Runtime stores task and session state locally.
4. User and agent work.
5. Runtime closes or completes the session.

### 7.2 Client-Assisted Start

1. A skill or MCP client detects clear work intent.
2. The client calls existing runtime primitives such as `start_task` or `continue_task`.
3. Tracking begins without requiring new product-only commands.

### 7.3 Resume After Pause

1. User or client sees the prior worked task.
2. Runtime starts a new session on that same task.
3. Total elapsed time remains attached to the task.

### 7.4 Complete And Close Out

1. User or client detects that work is done.
2. Runtime marks the task complete.
3. System prepares a concise summary.
4. System offers optional external updates after confirmation.

### 7.5 End-Of-Day Review

1. User asks for today's summary.
2. Runtime returns tasks worked, tasks completed, total time, and per-task breakdown.
3. Later versions add time-composition breakdown by category.

---

## 8. Functional Requirements

### 8.1 Runtime Requirements

- The system must store tasks and sessions locally.
- A task must have a stable `task_id`, title, state, and accumulated elapsed time.
- A task may have multiple sessions over time.
- A task may not have more than one open session for the same task at once.
- The runtime should support multiple open sessions across different tasks if the client semantics require it.
- The runtime must support closing a session without completing the task.
- The runtime must support explicit completion.

### 8.2 Identity Requirements

- The system must support both human-readable task titles and external identifiers such as `LIN-123`.
- External identifiers should be preserved as first-class task identity when available.
- The system should support optional metadata that links tasks to upstream systems later.

### 8.3 Summary Requirements

- The system must return daily totals.
- The system must return per-task totals.
- The system must support end-of-task summary generation.
- Summaries must remain useful even when advanced integrations are unavailable.

### 8.4 Classification Requirements

- The product must eventually classify elapsed time into meaningful buckets.
- Initial classifier buckets are:
  - `USER_ACTIVE`
  - `AGENT_EXECUTING`
  - `USER_REVIEWING`
  - `IDLE`
  - `BLOCKED`
- Classification should be additive to the runtime, not a replacement for it.

### 8.5 Interface Requirements

- Core runtime operations must be accessible from the CLI.
- Core runtime operations must be accessible from MCP.
- Skills and clients should be able to orchestrate start and completion using existing runtime primitives.
- We should avoid adding command surface area that only encodes one specific skill workflow.

### 8.6 Post-Back Requirements

- External updates must be opt-in and confirmed by the user.
- Linear is the first target integration.
- Slack and Git-related closeout flows are later targets.

### 8.7 Privacy Requirements

- Local storage is the default.
- No external write should happen without clear confirmation.
- Deeper logging must be minimal by default and explicit when expanded.

---

## 9. Sequencing

### 9.1 Foundation

Ship and stabilize the runtime:

- local task/session model
- CLI + MCP parity
- explicit start, continue, close, complete
- day summary and per-task totals

This is the minimum usable base.

### 9.2 Differentiator

Build the classifier and closure loop:

- time composition buckets
- end-of-task summary generation
- confirmed Linear post-back

This is where the product becomes meaningfully different from generic timers.

### 9.3 Expansion

Expand input and output surfaces:

- richer client behaviors
- Claude Code refinement
- Cursor and Windsurf support
- Slack and Git integrations
- broader signal ingestion if proven useful

---

## 10. Success Criteria

### 10.1 Product Success

- A real task can be tracked end-to-end locally without friction.
- End-of-day review matches the user's mental model closely enough to be trusted.
- The system is useful even before advanced automation is added.

### 10.2 Differentiator Success

- The time classifier produces insights the user could not have derived from simple wall-clock tracking.
- Human vs agent vs review vs idle distinctions change how the user reflects on work.

### 10.3 Closure Success

- Task summaries save real follow-up effort.
- External post-backs reduce missed updates instead of creating more friction.

### 10.4 Failure Conditions

- Users abandon the tool because tracking still feels manual
- the classifier is noisy enough that users do not trust it
- closeout suggestions are more annoying than helpful

---

## 11. Open Questions

1. What is the best signal set for distinguishing `AGENT_EXECUTING` from `USER_REVIEWING`?
2. How much session context should be stored locally for later summary generation?
3. What minimum metadata is required for reliable Linear post-back?
4. When, if ever, do dedicated runtime commands for auto-triggering become justified?
5. How should multiple concurrent tasks be presented in status and summaries without becoming noisy?

---

## 12. Decision Log

- `2026-04-23`: This document replaces the prior vision memo and becomes the single source of truth.
- `2026-04-23`: Auto-trigger is defined as a client/integration behavior, not the core product.
- `2026-04-23`: The product thesis is task-level observability plus time composition plus closure, not planning UX.
