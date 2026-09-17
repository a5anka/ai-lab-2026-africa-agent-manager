# Module 02 — Observability: seeing inside a single request

**Duration:** 20 min

Module 00 ended with one line of evidence per request:

```
INFO:     127.0.0.1:52118 - "POST /chat HTTP/1.1" 200 OK
```

Underneath that line the model was called more than once, chose its own
tool calls, and spent tokens. This module is about getting all of that
back — and about the fact that you already have it, because it started
the moment the agent was deployed in module 01.

## Zero-code auto-instrumentation

The traces exist because Agent Manager instruments the agent for you at
deploy time. Before anything else, check what is in
`agent/requirements.txt`:

```bash
grep -i -E 'otel|opentelemetry|traceloop' ../agent/requirements.txt
# → (no output)
```

No OpenTelemetry package. No SDK, no `init_tracing()`, no decorators, no
exporter configuration. The agent is byte-for-byte what module 00 ran on
a laptop.

Agent Manager injects an **init container** that pre-installs the
Traceloop SDK into the agent's Python environment at deploy time. It is
on by default — there is no `--enable-tracing` flag anywhere in the CLI,
only its opposite:

```bash
amctl agent create --help | grep instrumentation
# →   --no-auto-instrumentation   Disable automatic instrumentation
```

Because of that default, **every agent you deploy arrives instrumented** —
including the ones written long before anyone on the team was thinking
about traces. You get the coverage without having to run a campaign to
get it.

## Step 1 — Make some traffic

You cannot read traces you do not have. `seed-traffic.sh` sends seven
requests chosen to produce *different shapes*, not just volume:

```bash
export AGENT_URL=...     # from module 01, step 3
export AGENT_KEY=...     # from module 01, step 4

./seed-traffic.sh        # about 25 seconds
```

| # | Prompt | Shape | Spans |
|---|---|---|---|
| 1 | Pool hours | Answered from the system prompt — **no tool call** | 8 |
| 2 | Honeymoon suite in June | One tool call | 16 |
| 3 | Junior vs presidential, 3 nights | The same tool **twice, from one model turn** | 18 |
| 4 | Vegetarian room service | A different tool | 16 |
| 5 | Dinner in, outdoors tomorrow | **Two different tools** in one request | 18 |
| 6 | Two turns in one session | Input tokens grow on the second turn | 16 each |

Those span counts are from a real run, and the pattern in them is worth
more than any single number: **the span count tells you what the agent
decided to do.** Eight means it never called a tool. Sixteen means one
tool call and two model calls. Eighteen means two tool calls.

You did not choose those counts and neither did the platform. The model
did, at runtime, per request.

## Step 2 — Look inside one request

In the console, open the agent and pick **OBSERVABILITY → Traces** in the
sidebar. Each row is one end-to-end invocation. Click the comparison
request — junior versus presidential — to expand it.

> **If it says "No traces found", check the time range before anything
> else.** The picker opens on a short window, and a trace from earlier
> falls outside it. Widen it and the rows appear.

What you get is a tree, not a log. Stripped to the spans that matter:

```
invoke_agent LangGraph                        ← root: the whole request
  LangGraph.workflow
    execute_task agent
      ChatOpenAI.chat                         ← model call 1: decide what to do
    execute_task tools
      execute_tool check_room_availability     ← junior
    execute_task tools
      execute_tool check_room_availability     ← presidential
    execute_task agent
      ChatOpenAI.chat                         ← model call 2: write the answer
```

The real tree has more nodes than this — LangGraph emits its own
`call_model`, `RunnableSequence`, `Prompt` and `should_continue` steps
around each of the above. That is the framework's internal structure, and
it is genuinely useful when you are debugging the graph. Ignore it for now.

The shape is the point. Nobody wrote it down — the model decided, at
runtime, to call `check_room_availability` twice and then call itself
again. The tree is the only place that decision is recorded.

Spans come in kinds, and the kind tells you what to expect on it:

| `kind` | Carries |
|---|---|
| `agent` | The root — end-to-end latency, the whole request |
| `llm` | Model name, input and output tokens, finish reason, the messages |
| `tool` | Tool name, the arguments the model chose, what came back |
| `chain` | Framework plumbing between the above |

## Step 3 — Three questions a trace answers

The span tree is not a feature tour. It exists to answer three questions
you could not answer in module 00 — one for each property from the
opening.

### Where did the time go?

Read the durations down the tree and compare the `llm` spans against
everything else. On a tool-using request the model calls dominate: they
are network round-trips to a provider, while the tools are local work
measured in milliseconds.

That is worth knowing before anyone optimises the wrong thing. "The agent
is slow" is nearly always "the model was called more times than you
thought", not "the tools are slow" — and the trace is what tells you
which.

### What did it cost?

Open an `llm` span and read its attributes. These names are the
OpenTelemetry GenAI semantic conventions, so they are the same whatever
model or framework produced the span:

| Attribute | What it gives you |
|---|---|
| `gen_ai.request.model` | The model actually used |
| `gen_ai.usage.input_tokens` | Tokens sent on this call |
| `gen_ai.usage.output_tokens` | Tokens returned by this call |
| `gen_ai.response.finish_reasons` | Why it stopped — `tool_call` or `stop` |

Now compare the **two** `llm` spans in the same request. The second
call's input is always the larger one: nothing about the guest's question
changed, but the tool results were appended to the conversation before
the model was asked again.

That is the mechanism behind agent spend. You are not billed per request,
you are billed per model call — and a request decides at runtime how many
of those it needs, and how much context each one carries. Request 6 in the
seed script shows the same effect across turns of a conversation instead
of within one request.

Sum the `llm` spans for the cost of the whole request — the console shows
each one's tokens on the span.

### Why did it say that?

Tool spans carry the arguments the model chose and the value that came
back. For the comparison request they read:

```
execute_tool check_room_availability   {"nights":3,"room_type":"junior"}
execute_tool check_room_availability   {"nights":3,"room_type":"presidential"}
```

The guest wrote *"Compare a junior suite and the presidential suite for a
3-night stay."* Nothing in that sentence is `room_type` or `nights`. The
model extracted both, twice, and picked the enum values the tool accepts.

That is the closest thing an agent has to a stack trace — and it is the
first place to look when an answer is wrong but the code is fine.

## Step 4 — The same data, in the terminal

Everything above has a CLI path. These steps use `amctl`, which connects
to a self-managed install today — see the
[repo README](../README.md#prerequisites).

List recent traces — pass `--limit`, it defaults to 10:

```bash
amctl agent traces grand-meridian-concierge \
  --project default --env default --since 30m --limit 50 --json \
  | jq -r '.data.traces[] | "\(.traceId[0:8])  \(.spanCount) spans  \(.durationInNanos/1000000|round)ms"'
```

```
dd45e286  16 spans  2598ms
5541b9f2   8 spans  3700ms
```

That is the index the console's Traces view gives you, in a form you can
pipe. Span count is the useful column: it tells you what the agent
decided to do before you open anything.

For the inside of a single request — the span tree, the timings, the
tokens per model call — use the console. It draws that better than a
terminal will, and step 2 already did it.

What the terminal is for is everything you cannot click: filtering across
a window, and piping traces into whatever you already use.

**Use `traces export`, not `trace`.** They return different things:

| Command | Returns |
|---|---|
| `amctl agent trace <traceId>` | Flat span list — names, kinds, parents, durations. **No attributes.** |
| `amctl agent trace <traceId> --span <spanId>` | One span in full, attributes included |
| `amctl agent traces export` | Every trace in the window, every span, attributes included |

The middle column is the trap: attributes are where the token counts and
the tool arguments live, so anything that reads them wants `export`.

## Step 5 — Finding the request worth looking at

Reading one trace is easy when you already know which one is interesting.
In production you do not. `amctl agent traces` ships five built-in
conditions for exactly that:

```bash
amctl agent traces grand-meridian-concierge \
  --project default --env default --since 24h \
  --condition high_latency --max-latency 3000 --json
```

| Condition | Finds |
|---|---|
| `error_status` | Requests that failed |
| `high_latency` | Slower than `--max-latency` (default 30000 ms) |
| `high_token_usage` | More tokens than `--max-tokens` (default 10000) |
| `tool_call_fails` | Tool invocations that did not succeed |
| `excessive_steps` | More spans than `--max-spans` (default 40) — the agent that would not stop |

`excessive_steps` is the one with no equivalent in ordinary services. A
loop that never converges is expensive rather than loud: every individual
step is fast, so no latency alert fires, and it returns `200 OK` the whole
time. A span-count threshold is how you find it — and step 1 already
showed that span count tracks what the agent decided to do.

> **Reading the result count.** A filtered response reports it as
> `data.count`, an unfiltered one as `data.totalCount`, so
> `jq '.data.count // .data.totalCount'` covers both.

## Step 6 — The tool the agent could barely use

Ask the most ordinary question a hotel guest asks, three times:

```bash
for i in 1 2 3; do
  curl -s -X POST "$AGENT_URL/chat" \
    -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_KEY" \
    -d "{\"message\":\"Can you recommend somewhere to eat near the hotel?\",\"session_id\":\"diag-$i\",\"context\":{}}" \
    | jq -r '.response' | head -3
done
```

You will get two different kinds of answer. Most of the time, a good one:

```
I recommend the following dining options near The Grand Meridian:
1. L'Ardoise - A French bistro, just a 4-minute walk away...
```

And sometimes this:

```
I'm sorry for the inconvenience. I can certainly provide restaurant
recommendations near the hotel. Would you like me to do so?
```

Same question, same agent, same code. One reply is what you built; the
other apologises for nothing and asks the guest to ask again. Both are
`200 OK`, and the runtime logs are identical.

An agent that is *mostly* fine is the hardest kind to act on. There is
nothing to reproduce and nothing to report — until you look at the tool
spans, where all three requests say the same thing:

| Call | Input | Output |
|---|---|---|
| 1 | `{"category": "dining"}` | `{"error": "Unknown category. Available: restaurants, family, nightlife, outdoors."}` |
| 2 | `{"category": "restaurants"}` | `{"category": "restaurants", "recommendations": [...], "count": 3}` |

**Every one of those requests got the first call wrong.** The good answers
are the model noticing the error, working out the real category name from
it, and trying again — a second round trip and a second set of tokens,
every time anyone asks about food. The bad answer is the same first call,
on a turn where the model gave up instead of retrying.

**Why did it ask for `dining`?** Because that is what we told it to ask
for. The description shipped to the model lists the categories, and the
list is wrong:

```
category: One of: dining, family, nightlife, outdoors.
```

The data in `agent/hotel_data.py` is keyed `restaurants`, `family`,
`nightlife`, `outdoors`. Three of the four match. One does not, and it is
the one every hungry guest hits.

The model was not confused and it did not hallucinate. It read the
interface we gave it and used it exactly as documented. The bug is in the
sentence, and the sentence is in the prompt the model sees — which is why
nothing in your tests, your types or your status codes has an opinion
about it.

### The fix

`agent/tools.py` maintains that list two ways, and picks between them with
an env var read at startup:

| `TOOL_DOCS` | The description is |
|---|---|
| `handwritten` (default) | typed out by hand — and drifted from the data |
| `generated` | derived from `RECOMMENDATIONS`, so it cannot drift |

So the fix is configuration, not code, and there is nothing to rebuild:

```bash
amctl agent deploy grand-meridian-concierge \
  --project default --env TOOL_DOCS=generated --yes
```

Wait for `active`, ask the same question, and read the tool spans again:

| Call | Input | Output |
|---|---|---|
| 1 | `{"category": "restaurants"}` | `{"category": "restaurants", "recommendations": [...], "count": 3}` |

One call, the right call, every time — and the answer names L'Ardoise
without being asked twice.

> **The durable version of this fix is the second row of that table.** A
> tool description is an interface that a model reads and no compiler
> checks: nothing in Python objects to a docstring that lies about its own
> data. Hand-written descriptions drift the moment the data moves.
> Generating them from the thing they describe is how you stop shipping
> this bug — and traces are how you find the one you already shipped.

## Step 7 — Ask in English

You already installed what this needs. The `manage-agent` skill from
module 01 taught your assistant `amctl`, and traces are part of what it
covers — its `triage.md` walks build → logs → metrics → traces in that
order, and knows which conditions to reach for.

So there is nothing to set up. Ask:

> *"Look at the last hour of traces for grand-meridian-concierge in
> default. Which request was slowest, and where did the time actually
> go?"*

The assistant lists the traces, picks the outlier, pulls its spans and
reads the durations back to you. Same data as step 4 — the difference is
that you did not have to know the shape of the JSON to ask the question.

Then ask it the question this module opened with, and watch it pick its
own route:

> *"Did any tool call fail in the last hour without the request
> failing?"*

## How the traces actually get there

Worth understanding, because it explains both the zero-code part and the
one knob you will eventually need.

At deploy time, AMP injects an init container that installs a pinned
**Traceloop SDK** version into the agent's Python environment. The
version is chosen by the **AMP instrumentation version** you select at
create time — which means a deployed agent does not silently move to a
new SDK when the platform default advances. Reproducibility by default.

Traceloop instruments a fixed catalogue of libraries automatically: the
major LLM providers, the major agent frameworks, the major vector stores,
and MCP tool calls. This lab is on LangGraph and OpenAI, so all of it is
covered. If your framework is not on that list, auto-instrumentation gets
you less, and you emit spans yourself against AMP's published contract —
OpenTelemetry GenAI semantic conventions (`gen_ai.*`, `db.*`) plus a few
`traceloop.*` keys for what OTel has not standardised yet.

**Sampling.** Every trace is exported by default, which is right for a
lab and wrong for an agent serving real volume. Sampling is a head-based
decision made inside the agent process, via the standard OpenTelemetry
environment variables — `OTEL_TRACES_SAMPLER` and
`OTEL_TRACES_SAMPLER_ARG` — set like any other env var on the deployment.

## What this still does not tell you

Traces answer *what happened*. They do not answer *was it any good*.

Nothing in this module would have flagged a confident, well-formed,
fast, cheap answer that quoted a room rate the hotel does not charge.
Every span would be green. The latency would be fine. The token count
would be unremarkable.

Step 6 is the closest it gets, and it still needed you to go looking. The
trace named the bug once you suspected one, but nothing raised a hand —
the apology and the good answer came back through the same green spans,
because nothing was scoring either of them.

That gap is module 03.

## Going further

- [Observability concepts](https://wso2.github.io/agent-manager/docs/) — the full attribute contract and the manual-instrumentation path
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — where `gen_ai.usage.input_tokens` and friends are defined
- `amctl agent traces export --since 24h` — bulk dump of full span data, for analysing traffic outside the console
- **A dedicated observability MCP server** (`am-obs-mcp`) ships alongside the lifecycle one, with tools for logs, metrics, traces, trace details and span details. Step 7 does not need it — the `manage-agent` skill already drives the CLI — but if you would rather your assistant read the API directly than shell out, ask your instance where it lives: `curl -s <your-api-base-url>/api/v1/config` returns an `observerBaseUrl`, and `/mcp` on that host is the endpoint. It has its own client ID (`am-obs-mcp`) and callback port, so a token issued for the lifecycle server will not work on it.

---

Previous: [Module 01 — Build & Deploy](../01-build-deploy/README.md) ·
Next: [Module 03 — Evaluation](../03-evaluation/README.md)
