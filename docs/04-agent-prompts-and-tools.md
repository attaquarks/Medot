# 04 · Agent Prompts & Tool Definitions

Each agent = a **system prompt** (persona + policy) + a **tool registry**. The reasoning loop
lives in [`agents/base.py`](../src/aia/agents/base.py).

## 4.1 Tool-call convention

To work even with small local models that lack native function-calling, the model emits a fenced
block; the runtime executes it and feeds the result back:

````text
```tool
{"name": "log_meal", "arguments": {"description": "2 eggs and toast"}}
```
````

The loop runs up to `MAX_TOOL_HOPS` (4) tool round-trips, then the model writes the final plain-text
WhatsApp reply. When deployed on a function-calling-capable cloud model, native `tool_calls` can be
enabled in the service layer — same registries.

## 4.2 Business Assistant — system prompt

Full text: [`agents/business/prompts.py`](../src/aia/agents/business/prompts.py). Core policy:

- **Read freely, act carefully.** Visible third-party actions (send email, move/cancel meeting, place call) require an unambiguous instruction; otherwise ask one crisp question.
- **Escalate** high-stakes/urgent/angry/legal/financial matters to the principal on WhatsApp.
- **Keep CRM memory** of contacts; never invent availability, prices, or commitments.

## 4.3 Business tool catalog

| Tool | Arguments | Action |
|---|---|---|
| `list_events` | date | List calendar events for a day |
| `check_availability` | date_range, duration_min | Find free slots (freeBusy) |
| `create_meeting` | title, start, end, attendees | Create event + invite |
| `reschedule_meeting` | event_id, new_start, new_end | Move an event |
| `cancel_meeting` | event_id | Cancel an event |
| `inbox_summary` | max_results | Recent inbox with sender/subject/snippet |
| `draft_email` | to, subject, body | Create a draft (no send) |
| `send_email` | to, subject, body | Send (audited) — explicit approval only |
| `add_task` | title, due_at | Add follow-up/deadline |
| `list_tasks` | — | List open tasks |
| `remember_client` | name, fact | Persist CRM fact + semantic memory |
| `escalate` | reason, detail | WhatsApp the principal immediately |

Source: [`agents/business/tools.py`](../src/aia/agents/business/tools.py). A `place_call` tool wires to
the Twilio provider (see [05](05-integrations.md)).

## 4.4 Health & Diet Coach — system prompt

Full text: [`agents/health/prompts.py`](../src/aia/agents/health/prompts.py). Core policy:

- Turn natural-language food into a `log_meal` call; always report remaining calories afterward.
- Coach on **trends**, celebrate wins, flag unhealthy patterns with one concrete fix.
- **Not a doctor** — defer medical/ED/pregnancy concerns to professionals.

## 4.5 Health tool catalog

| Tool | Arguments | Action |
|---|---|---|
| `log_meal` | description | Estimate kcal+macros (provider→LLM fallback), log, return today's status |
| `log_weight` | weight_kg | Record a weigh-in |
| `log_exercise` | kind, duration_min | Log workout; estimate calories burned (METs) |
| `daily_status` | — | Consumed/burned/remaining vs target + protein |
| `set_goal` | goal, target_weight_kg, weekly_kg_change | Recompute daily calorie target |
| `weekly_report` | — | 7-day avg calories, weight trend, workout count |

Source: [`agents/health/tools.py`](../src/aia/agents/health/tools.py). Math is pure & unit-tested in
[`agents/health/nutrition.py`](../src/aia/agents/health/nutrition.py) (BMR Mifflin–St Jeor, TDEE,
calorie targets with a safe 1200 floor, MET burn, projection).

## 4.6 Proactive (push) behaviours

| Agent | Trigger | Output |
|---|---|---|
| Business | morning schedule | "☀️ Morning brief" — meetings, urgent emails, open follow-ups |
| Business | urgent email detected | instant WhatsApp escalation |
| Health | end of day | "🌙 Daily check-in" — vs targets + a tip |
| Health | weekly | "📊 Weekly report" — trend & adherence |

These are fired by a scheduler (APScheduler/cron) calling the workflow functions
(`daily_summary`, `daily_accountability`, `weekly_checkin`). On the official WhatsApp Cloud API,
proactive messages outside the 24-hour window must use approved **templates** (see [05](05-integrations.md)).
