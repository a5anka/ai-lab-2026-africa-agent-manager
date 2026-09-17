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

Sum the `llm` spans for the cost of the whole request. `trace-tree.py` in
step 4 does that arithmetic and prints it on the first line.

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

## Step 4 — The same trace, in the terminal

Everything above has a CLI path. These steps use `amctl`, which connects
to a self-managed install today — see the
[repo README](../README.md#prerequisites).

List recent traces — pass `--limit`, it defaults to 10:

```bash
amctl agent traces grand-meridian-concierge \
  --project default --env default --since 30m --limit 50 --json \
  | jq -r '.data.traces[] | "\(.traceId[0:8])  \(.spanCount) spans  \(.durationInNanos/1000000|round)ms"'
```

Then pull full span data and render it:

```bash
amctl agent traces export grand-meridian-concierge \
  --project default --env default --since 30m --limit 20 --json \
  | ./trace-tree.py --trace <traceId-prefix>
```

`trace-tree.py` is in this directory — standard library only, no
dependencies. One run's output, so that you know what to expect rather
than what to match:

```
3c7483a3  18 spans · 2 model calls · 2 tool calls · 1,219 in / 163 out tokens

invoke_agent LangGraph                               2,345ms  ████████████████████████
  LangGraph.workflow                                 2,344ms  ████████████████████████
    execute_task agent                               1,071ms  ███████████
      execute_task call_model                        1,070ms  ███████████
      execute_task RunnableSequence                  1,069ms  ███████████
        execute_task Prompt                              0ms  █
        ChatOpenAI.chat                              1,068ms  ███████████   gpt-4o  494 in / 62 out
      execute_task should_continue                       1ms  █
    execute_task tools                                  69ms  █
      execute_tool check_room_availability              65ms  █   {"nights":3,"room_type":"junior"}
    execute_task tools                                   3ms  █
      execute_tool check_room_availability               1ms  █   {"nights":3,"room_type":"presidential"}
    execute_task agent                               1,197ms  ████████████
      execute_task call_model                        1,196ms  ████████████
      execute_task RunnableSequence                  1,195ms  ████████████
        execute_task Prompt                              0ms  █
        ChatOpenAI.chat                              1,194ms  ████████████   gpt-4o  725 in / 101 out
      execute_task should_continue                       0ms  █
```

Your durations and token counts will be different — they are a property
of the model and of what it decided to do, not of the platform. The shape
is what holds: a model call, the tool calls it chose, a model call.

Add `--attrs` to print every `gen_ai.*` attribute on every span.

**Use `traces export`, not `trace`.** They return different things:

| Command | Returns |
|---|---|
| `amctl agent trace <traceId>` | Flat span list — names, kinds, parents, durations. **No attributes.** |
| `amctl agent trace <traceId> --span <spanId>` | One span in full, attributes included |
| `amctl agent traces export` | Every trace in the window, every span, attributes included |

`trace-tree.py` accepts either of the bulk forms. Given the flat one it
draws the tree and the timings and simply has no tokens to show.

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

## Step 6 — The failure the response hid

Ask for a stay the hotel cannot price:

```bash
curl -s -X POST "$AGENT_URL/chat" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_KEY" \
  -d '{"message":"I would like the presidential suite for 45 nights starting 2026-11-01. What is the total?","session_id":"diag","context":{}}'
```

The reply is a good one. Mine was:

> *"I apologize, but stays longer than 30 nights require special
> arrangements. May I connect you with our reservations team to assist
> with this?"*

Polite, specific, plausible. `200 OK`. Now go looking for it with the
condition that ought to find it:

```bash
amctl agent traces grand-meridian-concierge \
  --project default --env default --since 30m \
  --condition tool_call_fails --json | jq '.data.count'
# → 0
```

Zero. The trace list agrees — that request came back with
`"status": {"errorCount": 0}`. And yet a tool call in it did fail. Export
the trace and read the tool's own output:

```bash
amctl agent traces export grand-meridian-concierge \
  --project default --env default --since 30m --limit 20 --json \
  | ./trace-tree.py --tool-errors
```

```
dd45e286  check_room_availability
          reported: Nights must be an integer between 1 and 30.
          called with: {"check_in":"2026-11-01","nights":45,"room_type":"presidential"}
```

There it is, in the tool's recorded result.

**Why the condition missed it.** `agent/tools.py` says so in its own
docstring — *"Tools never raise into the agent loop"* — and it is a
completely ordinary way to write a tool:

```python
if not isinstance(n, int) or n < 1 or n > 30:
    return {"error": "Nights must be an integer between 1 and 30."}
```

The tool **returns** its failure instead of raising it. So the function
completed, the span carries a healthy status, and every layer above it —
`errorCount`, `--condition tool_call_fails`, any alert wired to either —
correctly reports a success, because that is what the code claimed. Span
status is your code's assertion, not the platform's guess.

**The fix has two halves, and the first one you can do right now.** The
evidence was never lost: the tool's arguments and its result are both on
the span, so the failure is findable even when it is not *flagged*. That
is what `--tool-errors` reads, and it turns a lucky catch into a check
you can run over any window:

```bash
amctl agent traces export grand-meridian-concierge \
  --project default --env default --since 24h --limit 100 --json \
  | ./trace-tree.py --tool-errors
```

Run it after any change and you will see every tool that quietly refused
to answer — which room types guests asked for and did not get, which
dates fell outside the window.

The second half belongs in the agent, and it is one line: raise instead
of returning, or set the span status yourself. Do that and this stops
being a report you remember to run — `--condition tool_call_fails` finds
it for you, `errorCount` counts it, and the alert you already have fires.
The platform was ready for that signal the whole time; nothing was
sending it.

> **The same shape, one layer up.** Try `"What does the Garden Villa cost
> per night?"` — a room type that does not exist. The reply is right, and
> the trace shows **no tool call at all**: the model answered from the
> tool's own schema, which lists the five real room types. Right answer,
> no data consulted. That is the distinction the response text cannot
> make for you and a trace can — and measuring it across many answers,
> rather than reading one, is module 03.

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

Step 6 is the near miss that makes the point. Reading one trace told you
a tool had quietly refused, and `--tool-errors` will tell you how often
it happens. Neither tells you whether the answers the agent *did* give
were any good — and you cannot read every trace.

That gap is module 03.

## Going further

- [Observability concepts](https://wso2.github.io/agent-manager/docs/) — the full attribute contract and the manual-instrumentation path
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — where `gen_ai.usage.input_tokens` and friends are defined
- `amctl agent traces export --since 24h` — bulk dump of full span data, for analysing traffic outside the console
- **A dedicated observability MCP server** (`am-obs-mcp`) ships alongside the lifecycle one, with tools for logs, metrics, traces, trace details and span details. Step 7 does not need it — the `manage-agent` skill already drives the CLI — but if you would rather your assistant read the API directly than shell out, ask your instance where it lives: `curl -s <your-api-base-url>/api/v1/config` returns an `observerBaseUrl`, and `/mcp` on that host is the endpoint. It has its own client ID (`am-obs-mcp`) and callback port, so a token issued for the lifecycle server will not work on it.

---

Previous: [Module 01 — Build & Deploy](../01-build-deploy/README.md) ·
Next: [Module 03 — Evaluation](../03-evaluation/README.md)
