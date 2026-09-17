# Module 03 — Evaluation: measuring something that answers differently every time

**Duration:** 18 min

Module 00 ended with eight passing unit tests. Module 02 ended with a
complete span tree. Neither of them can tell you whether the agent was
*any good*.

Picture the answer that would hurt most: fluent, fast, cheap, confident,
and quoting a room rate the hotel does not charge. Every span green. The
latency fine. The token count unremarkable. All eight tests still pass,
because they test tool arithmetic and this was never a tool problem.

This module is about the measurement that catches it.

## Why the tests you know don't work here

Run module 00's suite twice and you get the same result twice. Ask the
agent the same question twice and you do not:

```bash
# same prompt, two calls
curl -s -X POST "$AGENT_URL/chat" -H "X-API-Key: $AGENT_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"message":"What can you tell me about the deluxe suite?","session_id":"a","context":{}}' | jq -r .response
```

Two runs produce two different sentences. Both may be correct. Neither is
equal to the other, and equality is what an assertion is made of.

So quality needs a different instrument: not a pass/fail against a fixed
string, but a **score**, produced by something that reads the answer.

## How evaluation works here

Three properties of the design matter more than any individual
evaluator, and they are what make this practical rather than aspirational.

**It runs on traces, not on the agent.** Evaluation reads the execution
records module 02 produced. It never sits in the request path.

**So it cannot slow the agent down.** There is no evaluation step between
your guest and their answer. Scoring happens afterwards, out of band.

**And it works backwards in time.** Because the input is stored traces,
you can point a *new* evaluator at *old* traffic and get scores for
requests that happened before you thought of the question. You do not
have to re-run the agent, and you do not have to wait for new traffic to
find out whether last week was fine.

The third property is the one worth remembering. Step 6 puts it to use.

## Step 1 — Create a monitor

A **monitor** is a configured evaluation job: a set of evaluators, an
agent, an environment, and a window of traces to run over.

1. Open the agent in the console and click the **Evaluation** tab.
2. Click **Add Monitor**.
3. Give it a title. The identifier fills itself in.
4. For **Data Collection Type**, choose **Past Traces** and set the window
   to cover the traffic module 02 generated. (**Future Traces** is the
   other option — a recurring schedule, minimum five minutes, for ongoing
   production monitoring. Come back to it in step 6.)
5. Pick evaluators from the grid, configuring each as you add it. Take
   five, and deliberately take both kinds:

   **Rule-based** — deterministic, instant, free:

   | Evaluator | Level | Set |
   |---|---|---|
   | **Length Compliance** | trace | `min_length` 20, `max_length` 2000 |
   | **Latency Performance** | trace | `max_latency_ms` 5000 |
   | **Content Safety** | trace | `prohibited_strings`: `guarantee`, `refund`, `free upgrade` · `prohibited_patterns`: a card-number and an email pattern |

   **LLM-as-judge** — a model reads the trace and scores it:

   | Evaluator | Level | Set |
   |---|---|---|
   | **Completeness** | trace | `model` `openai/gpt-4o` · `temperature` `0.0` |
   | **Tone** | llm | `model` `openai/gpt-4o` · `temperature` `0.0` · `context` `luxury hotel concierge` |

6. The judges need a model, so a **LLM Providers** section appears in the
   evaluator configuration panel. Pick a provider, paste an API key, and
   click **Add**. You do this once per monitor; every judge in it shares
   the credentials.

7. Click **Create Monitor**. A Past-Traces monitor starts evaluating
   immediately.

Those two judges are chosen for a reason.

**Completeness** checks whether the answer addressed everything the guest
asked, and the traffic from module 02 gives it real work to do. Two of
those prompts are deliberately multi-part — *"compare a junior suite and
the presidential suite"* and *"what can we order to the room, and what is
worth doing nearby tomorrow"*. An answer that covers the first half of
either and quietly drops the second is a specific, recognisable failure,
and it is not one any rule can see.

**Tone** is **LLM-level**, so it scores every model call individually
rather than the final answer — which is how you catch something off-brand
in an intermediate reasoning step that the final answer smoothed over. It
takes a `context` string, so "luxury hotel concierge" is a different bar
from "casual chat".

Picking one of each level also makes the dashboard in step 2 more
interesting, because the summary breaks results out per level.

Swap in **Helpfulness** or **Relevance** if you prefer — both are
trace-level and both apply to every request. `Completeness` also takes an
optional `success_criteria` string if you want to spell out what a
complete answer looks like for your agent.

> **Fill in the optional config as you add each evaluator.** Content
> Safety with no prohibited strings and no patterns has nothing to look
> for, so it reports **skipped** rather than inventing a verdict — which
> is the honest answer, and correctly kept out of the average. Give it
> real values and it starts contributing a real score.
>
> `model` is the one setting with no default: judges will not run without
> it. Keep `temperature` at `0.0` — you want the same trace to score the
> same way twice.

Give it a few minutes. The rule-based evaluators finish almost instantly;
the judges make a model call per evaluation, and `Tone` makes one per
model call in every trace. It is a job, not a page load.

## Step 2 — Read the dashboard

Click the monitor to open it.

- **Agent Performance** — a radar chart, one axis per evaluator, so
  strengths and weaknesses read at a glance.
- **Evaluation Summary** — the weighted average and the total count,
  broken out per level. Both a trace row and an LLM row appear, because
  you configured an evaluator at each: the trace count matches your
  traffic, while the LLM count is higher, since `Tone` ran once per model
  call and most requests make two.
- **Performance by Evaluator** — a time series per evaluator. This is the
  regression detector: a line that steps down after a Tuesday deploy is
  the whole reason to run this continuously.
- **Score breakdown by model** — one row per model used across the
  evaluated traces, with the LLM-level scores for each. With one model in
  play it is a single row; point two agents at two models and this is how
  you compare them on identical traffic.
- **Run history** — every run, with status, its trace window, and logs.
  Individual runs can be re-run.

Then go back to **Traces**, because the scores are there too:

- the traces table gains a **Score** column, colour-coded
- selecting a span shows score chips next to duration and tokens
- a **Scores** tab gives each evaluator's result with its **explanation**

Read the explanations, not just the numbers. A score tells you something
changed; the explanation tells you what, in a sentence, per trace — so you
can act on a result without opening the trace to work out what the
evaluator objected to.

## Step 3 — What you just ran

You used both kinds of evaluator in that monitor, and the difference
between them is not cosmetic.

| | Rule-based | LLM-as-judge |
|---|---|---|
| How it decides | Python, deterministic | A model reads the trace and scores it |
| Speed | Instant | Seconds |
| Cost | Free | A model call per evaluation |
| Same trace twice | Identical score | Near-identical |
| Right for | latency, length, token budget, required tools, prohibited content | accuracy, helpfulness, groundedness, tone, reasoning |

Read the source of a built-in rule to see how little magic is involved —
every built-in ships its implementation:

```bash
amctl api --project default '/orgs/{org}/evaluators' -X GET -f limit=100 \
  | jq -r '.evaluators[] | select(.displayName=="Content Safety") | .source'
```

And list what your instance offers, with levels and types. **Pass a
`limit`** — the endpoint pages at 20 and there are more than that:

```bash
amctl api --project default '/orgs/{org}/evaluators' -X GET -f limit=100 \
  | jq -r '.total as $t | .evaluators[] | "\(.type)\t\(.level)\t\(.displayName)"' \
  | sort
```

At `1.0.0` that is **24 built-ins — 9 rule-based and 15 LLM-as-judge** —
covering latency, length, token budget, tool coverage and prohibited
content on the rule side, and accuracy, groundedness, helpfulness,
relevance, completeness, clarity, reasoning quality, error recovery, path
efficiency, instruction following, coherence, conciseness, safety and
tone on the judge side.

Check `.total` against the number of rows you got back before assuming
you have seen the whole catalogue.

### Three levels

The same list shows a **level** per evaluator, and it decides what the
evaluator sees and how often it runs. You have already seen two of the
three in action — `Completeness` at trace level, `Tone` at LLM level:

| Level | Sees | Runs |
|---|---|---|
| **Trace** | the whole request, input to output | once per trace |
| **Agent** | one agent's steps and decisions | once per agent execution |
| **LLM** | a single model call and its messages | once per model call |

You do not configure any iteration logic. `Tone` ran once per model call
without being told to, which is why its evaluation count in step 2 was
roughly double the trace count.

## Step 4 — Write an evaluator for your own domain

The built-ins cover the dimensions every agent shares. They cannot cover
the one from the top of this page, because only you know what your rooms
cost.

[`evaluators/room_rate_accuracy.py`](evaluators/room_rate_accuracy.py) is
a trace-level **code** evaluator that pulls every money figure out of the
answer and checks it against the published price list, allowing for
nightly multiples of a stay length the guest actually asked about.

Custom evaluators are written in the console — **Evaluation → Evaluators
→ Create Evaluator** — which is a slow loop to iterate in. So test it on
your machine first:

```bash
cd evaluators
./harness.py room_rate_accuracy.py
```

```
real · one room                            100%   All 1 money figure matches ...
real · a 3-night total                     100%   All 2 money figures match ...
real · no prices at all                    SKIP   No money figures in the response
caught · a rate we do not charge             0%   1 of 1 money figure not on the price list ...
missed · plausible arithmetic, wrong room  100%   All 2 money figures match ...
```

[`harness.py`](evaluators/harness.py) defines the same `Trace` and
`EvalResult` objects the platform injects, runs your function against
sample traces, and prints the scores. A second to run, instead of a
save-and-wait-for-a-run cycle.

Then paste the block between the markers into the console editor. The
platform supplies the imports and the signature; you write the body.
Declare `valid_amounts` and `max_nights` as **config params** and the
same evaluator serves every property in the group, configured per
monitor.

> **`EvalResult.skip()` is not a zero.** Use it when the evaluator does
> not apply — no output, no prices, no retrieval step. Skips are tracked
> separately and excluded from the average, so an evaluator that honestly
> declines to judge does not drag the score down.
>
> The built-ins do the same, and some let you choose which. `Groundedness`
> and `Context Relevance` both take an `on_missing_context` setting:
> `skip` (the default) when the trace has no tool results or no retrieval
> step to check against, or `zero` to treat that as a failure instead.
> Neither is in the monitor you just built — worth knowing before you add
> one and wonder why an axis is empty.

## Step 5 — Where rules stop

Look at the harness output again. The last case scores 100% and should
not: *"$420 per night, or $760 for two nights"* is wrong for a $420 room,
but $760 is exactly two nights of the $380 junior suite, so a rule
holding only a price list cannot fault it.

No amount of regex fixes that. It needs something that can read which
room was being discussed — which is what a judge does, and why two of them
went into the monitor in step 1.

There is a built-in aimed squarely at this one: **Groundedness** checks
that factual claims are supported by the tool results in the same trace,
so a figure belonging to a different room is exactly what it is looking
for. Add it and choose its `on_missing_context` behaviour to suit.
**Accuracy** scores factual correctness more broadly, and **Safety** joins
`Tone` at the LLM level.

What no built-in can know is your house style:
[`evaluators/concierge_voice.md`](evaluators/concierge_voice.md) is a
prompt template that scores the five service standards written into
`agent/system_prompt.py` — grounded in tool data, answer first, in
character, no leaked plumbing, honest about limits. None of those five is
expressible as a rule, and all five are things a hotel would actually
fire someone over.

Add it in the console the same way, choosing **LLM-Judge** as the type
and pasting the prompt. It takes the same **Model**, **Temperature** and
**Criteria** settings as the built-in judges, and shares the monitor's LLM
credentials — nothing extra to configure.

## Step 6 — Score last week with this week's standards

You have just written two evaluators that did not exist when the traffic
in step 1 was served. Create a **second Past-Traces monitor** over **the
same window**, with the new evaluators added.

The agent is untouched. No rebuild, no redeploy, no new traffic. Within a
couple of minutes you have quality scores, against standards you invented
after the fact, for requests that were served before you thought of them.

That is not a thing you can do with tests. A test suite tells you about
the code you have now; it has nothing to say about yesterday.

Then make it ongoing: create a **Future Traces** monitor with the same
evaluator set and an interval. It starts within a minute, runs on
schedule, and the time series in step 2 becomes a regression alarm rather
than a snapshot.

## Step 7 — The same monitor, every time

The console is the right place to design a monitor. Once it is designed,
you want it identical on every agent and after every release. This step
runs on `amctl`, so it needs a self-managed install — see the
[repo README](../README.md#prerequisites):

```bash
./create-monitor.sh                       # defaults: this agent, last 6 hours
./create-monitor.sh my-other-agent 24
```

[`create-monitor.sh`](create-monitor.sh) reads the evaluator catalogue
from your org, builds the monitor body, and creates it.

As written it configures the **rule-based** subset of step 1's set, for one
practical reason: rule-based evaluators need no LLM credentials, so the
script runs anywhere without a secret to inject. Add the judges and their
provider configuration when you want them — nothing about this path is
rule-only.

Both kinds work in either monitor type. **Evaluator type and monitor type
are independent choices:** a Past-Traces run and a scheduled Future-Traces
monitor can each hold any mix of rules and judges, and a real quality bar
usually holds both — as step 1's does.

Read the result back:

```bash
amctl api --project default \
  '/orgs/{org}/projects/{project}/agents/grand-meridian-concierge/monitors/lab-quality-check/scores' \
  -X GET -f startTime=<start> -f endTime=<end> \
  | jq -r '.evaluators[] | "\(.evaluatorName)  mean=\(.aggregations.mean)  n=\(.count)  skipped=\(.skippedCount)"'
```

## Where this leaves you

| | |
|---|---|
| A score per trace | with an explanation you can act on |
| A trend per evaluator | so a regression shows up as a step down |
| Rules for what you can count | free, instant, deterministic |
| Judges for what you'd otherwise read | including standards only you know |
| Either kind, in either monitor | one-off over past traffic, or on a schedule |
| Retrospective scoring | new criteria, old traffic, no agent change |

One thing is still missing. All of this assumed the platform built and
deployed the agent — and in a real estate, most agents were not built
here.

That is module 04.

## Going further

- [Evaluation concepts](https://wso2.github.io/agent-manager/docs/) — the full built-in reference, all parameters, and the custom-evaluator data models
- Custom evaluator code cannot import `os`, `subprocess`, `socket`, `ctypes` or `importlib`, and dynamic `__import__()` is rejected at save time. Write evaluators that need none of them.
- Agent-level and LLM-level evaluators unlock two extra dashboard tables — score by agent, and score by model — which is how you compare models on the same traffic.

---

Previous: [Module 02 — Observability](../02-observability/README.md) ·
Next: [Module 04 — External Agents](../04-external-agents/README.md)
