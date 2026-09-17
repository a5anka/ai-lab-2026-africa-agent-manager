# Module 02 — Observability: seeing inside a single request

**Duration:** 15 min

Module 00 ended with one line of evidence per request:

```
INFO:     127.0.0.1:52118 - "POST /chat HTTP/1.1" 200 OK
```

Underneath that line the model was called more than once, chose its own
tool calls, and spent tokens. This module is about getting all of that
back — and about the fact that you already have it, because it started
the moment the agent was deployed in module 01.

## Nothing was added to the agent

Before anything else, check what is in `agent/requirements.txt`:

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

That default is the whole argument of this module: **every agent you
deploy arrives instrumented**, including the ones written long before
anyone on the team was thinking about traces. You get the coverage
without having to run a campaign to get it.

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

Everything above has a CLI path. List recent traces:

```bash
amctl agent traces grand-meridian-concierge \
  --project default --env default --since 30m --json \
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

`excessive_steps` is the one worth dwelling on. A loop that never
converges is a failure mode ordinary services do not have: it is
expensive rather than loud, every individual step is fast so no latency
alert fires, and it returns `200 OK` the whole time. A span-count
threshold is how you find it — and step 1 already showed that span count
tracks what the agent decided to do.

> **Reading the result count.** A filtered response reports it as
> `data.count`, an unfiltered one as `data.totalCount`, so
> `jq '.data.count // .data.totalCount'` covers both.

## Step 6 — Ask in English

Agent Manager ships a **second MCP server** dedicated to observability —
`am-obs-mcp` — separate from the lifecycle one. Seven tools:
`get_runtime_logs`, `get_build_logs`, `get_metrics`, `list_traces`,
`get_traces`, `get_trace_details`, `get_span_details`.

It runs on its own host. Ask your instance where:

```bash
curl -s <your-api-base-url>/api/v1/config
# → {"observerBaseUrl":"https://..."}
```

Append `/mcp`, and register it with your assistant. Note the dedicated
client ID and callback port — the observability server has its own, and a
token issued for the lifecycle MCP server will not work here:

```bash
claude mcp add --transport http agent-manager-observer <observerBaseUrl>/mcp \
  --client-id am-obs-mcp \
  --callback-port 33419
```

Then ask, in a sentence:

> *"Look at the last hour of traces for grand-meridian-concierge in
> default. Which request was slowest, and where did the time actually
> go?"*

The assistant calls `list_traces`, picks the outlier, calls
`get_trace_details`, and reads the span durations back to you. Same data
as step 4. The difference is that you did not have to know the shape of
the JSON to ask the question.

Pair it with the `manage-agent` skill from module 01 and the loop closes:
the skill knows the triage order, the observer MCP has the data.

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

That gap is module 03.

## Going further

- [Observability concepts](https://wso2.github.io/agent-manager/docs/) — the full attribute contract and the manual-instrumentation path
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — where `gen_ai.usage.input_tokens` and friends are defined
- `amctl agent traces export --since 24h` — bulk dump of full span data, for analysing traffic outside the console

---

Previous: [Module 01 — Build & Deploy](../01-build-deploy/README.md) ·
Next: [Module 03 — Evaluation](../03-evaluation/README.md)
