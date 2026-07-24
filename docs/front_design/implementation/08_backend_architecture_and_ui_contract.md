# 08 Backend Architecture And UI Contract

> Status: authoritative integration baseline, inspected 2026-07-24.
>
> Source of truth: `luminous/runtime/infrastructure/http.py`, runtime/application
> services, and domain models. This document supersedes assumptions based on the
> former prototype UI.

## Runtime Shape

The product runtime is intentionally split into four layers:

- `domain`: companion relationship state, presence, memory, scheduling, safety,
  and life-flow entities.
- `application`: `CompanionRuntime` orchestrates one conversation turn;
  `SchedulingService` owns reminders/calendar/notification preferences;
  `LifeFlowService` owns tasks, routines, activities, and diary entries.
- `infrastructure`: local stores, model client, notification bridge, worker, and
  `CompanionRequestHandler` HTTP server.
- `apps/companion-web/companion-ui`: static frontend directory served by that
  same HTTP server. Do not use the old `run.py` static-only server in production.

Start the integrated product with:

```bash
python -m luminous.runtime.infrastructure.http --mock
```

The default origin is `http://127.0.0.1:8000`; static assets and `/api/*` share
the origin. The handler forbids traversal, returns JSON errors, and supports
`GET`, `POST`, `PATCH`, `DELETE`, and `OPTIONS`.

## Core Conversation Contract

`POST /api/chat`

```json
{
  "message": "用户输入",
  "history": [{"role": "user", "content": "..."}]
}
```

Success returns at least `reply`, `presence`, `state`, `memory`, `ledger`,
`proactive`, `role_thinking`, and `role_action`. The server returns `400` for a
bad request, `503` for model-client failure, and `500` for an unexpected error.

Use the fields as follows:

- Render `reply` as the companion's actual answer.
- Drive ambient UI from `presence.heart_rate`, `presence.thought`,
  `presence.activity`, and `presence.caption`.
- Reconcile local ambient state with `state` after every turn and with
  `GET /api/state` on boot/refresh.
- Treat `memory.hits` and `memory.written` as private supporting context; do not
  make them noisy in the primary conversation surface.
- Keep `ledger`, trace identifiers, raw prompt data, and debug-only data out of
  the normal companion experience.

Never show any system prompt or chain-of-thought-like data. The primary UI may
use the already-shortened `presence` fields, not raw tracing content.

## Ambient Relationship State

`GET /api/state` returns the persisted companion state. Important fields:

- `mood`, `energy`, `support_need`, `risk_level`, `conversation_mode`.
- `relationship`: trust, intimacy, boundaries, familiarity, rupture, repair.
- `user_affect`, `companion_affect`, `interaction_rhythm`, and `drives`.
- `dnd_until`, `open_loops`, `proactive_readiness`, `relationship_arc`, and
  `attachment`.

These are signals for quiet environmental changes such as light, stillness,
proximity, and copy tone. Do not expose them as numerical gauges, personality
diagnoses, or an operational dashboard. `risk_level` must favor calm support
and safety copy; it must never become a game-like score.

## UI-Relevant API Surface

### Read models

- `GET /api/health`: runtime/model availability; use only for unobtrusive
  connection/error handling.
- `GET /api/state`: companion state.
- `GET /api/memory?q=&limit=`: memory retrieval.
- `GET /api/outbox?status=&limit=`: proactive messages and delivery state.
- `GET /api/reminders?status=&limit=` and `GET /api/calendar-events?limit=`.
- `GET /api/today?date=` and `GET /api/timeline?from=&to=&kind=&limit=`.
- `GET /api/tasks?status=&limit=`, `GET /api/routines?active_only=&limit=`,
  `GET /api/activities?status=&limit=`, `GET /api/diary-entries?date=&limit=`.
- `GET /api/settings/notifications`.

The following are developer/support-only and must stay behind an explicitly
enabled diagnostic surface: `GET /api/ledger`, `/api/trace`, `/api/jobs`,
`/api/memory/threads`, `/api/memory/links`, `/api/memory/evidence`, and
`/api/export`.

### Creation and confirmation

- Create `tasks`, `routines`, `activities`, `diary-entries`, `reminders`, and
  `calendar-events` with their respective `POST /api/<resource>` routes.
- `POST /api/diary-entries/draft` requests a draft.
- `POST /api/actions/preview` then `POST /api/actions/confirm` is the required
  two-step path for companion-initiated real-world actions. Supported actions:
  `create_task`, `complete_task`, `start_focus_session`, `checkin_routine`, and
  `draft_diary`.
- `POST /api/proactive/tick` triggers the proactive engine; normal users should
  never need a visible trigger. `POST /api/worker/tick` is developer-only.

### Mutations and state changes

- `PATCH /api/tasks/<id>`, `/api/tasks/<id>/steps/<step-id>`,
  `/api/routines/<id>`, `/api/diary-entries/<id>`, `/api/reminders/<id>`, and
  `/api/calendar-events/<id>` update resources.
- `POST /api/tasks/<id>/<action>` supports task steps/transitions;
  `POST /api/routines/<id>/checkin`,
  `POST /api/activities/<id>/<action>`, and
  `POST /api/reminders/<id>/(snooze|complete|cancel)` change active state.
- `DELETE` resource routes use soft status updates where appropriate.
- `POST` or `PATCH /api/settings/notifications` writes notification preferences.
- `POST /api/memory/update`, `/api/memory/forget`, `/api/outbox/feedback`, and
  `/api/outbox/receipt` support privacy and delivery feedback flows.

Every mutation must have loading, success, failure, retry, and an accessible
confirmation state. Do not optimistically claim a real-world action succeeded
until the backend response is successful.

## Worker And Proactive Behavior

`CompanionWorker` periodically runs state decay, proactive decisions, due
reminders, due routines, activity expiry, outbox delivery, memory consolidation,
and memory reindexing. The product UI should surface their meaningful outcomes
(a gentle arrival in the outbox, a due reminder, an updated Today view), never
the worker queue as a default product feature.

Respect `dnd_until` and notification preferences before presenting attention-
seeking prompts. A proactive message belongs in the companion's quiet arrival
surface, not as an intrusive modal.

## Frontend Baseline And Delegation Boundary

The current `apps/companion-web/companion-ui/` directory is empty. The next
implementation therefore creates the static frontend deliberately, rather than
trying to preserve a non-existent `app.js` or `styles.css`.

Gemini may create and edit only files in that frontend directory (plus direct
frontend assets needed there). It must not edit `.env`, Python backend files,
the runtime stores, or deployment configuration. Its first implementation must
use plain HTML/CSS/JavaScript and browser `fetch`, since the repository has no
frontend package manifest or build system.

## Acceptance Implications

- The app must boot against the integrated HTTP server on port 8000, not a
  standalone static server on port 8080.
- The conversation, Today/life-flow, notification preferences, outbox, memory
  privacy controls, and confirmation flow must call the real routes above.
- A failed API response must preserve user input and offer recovery without
  breaking the immersive scene.
- Diagnostic endpoints must not be visible in normal product navigation.
