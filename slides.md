---
marp: true
theme: default
paginate: true
---

<!--
Deck for session 1 of the Agent Manager lab, WSO2Con 2026 Africa.
Slides cover the 15-minute opening and the transitions between modules.
The modules themselves are demos, not slides.

Renders with Marp (`marp slides.md`) or reveal-md. Plain markdown otherwise.
Presenter notes are NOT in this file.
-->

# Running Agents Like Production Software

### WSO2Con 2026 Africa · Agent Manager lab, session 1

---

## The next 90 minutes

**15 min** — why agents need a control plane

**65 min** — building one, live

**10 min** — your questions

Everything demonstrated is in a public repo. Nothing here is a mock.

---

## First, let's be precise about what an agent is

```python
while not done:
    response = model(messages, tools)
    if response.tool_calls:
        messages += [run(call) for call in response.tool_calls]
    else:
        done = True
```

A loop. A model. Some tools. Some state.

That is genuinely all it is.

---

## Today's agent

**The Grand Meridian** — a hotel concierge.

LangGraph + FastAPI + OpenAI. About 300 lines.

```
POST /chat   { message, session_id, context }  →  { response }
```

Three tools: check availability · room service menu · local recommendations

**This code never changes for the rest of the session.**

---

## So why is this hard?

Not because the loop is complicated.

Because of four properties ordinary software does not have.

---

## 1. Same input, different output

```
$ ask "Compare a junior suite and the presidential suite"
→ "The Junior Suite offers a king bed..."

$ ask "Compare a junior suite and the presidential suite"
→ "Certainly! Let me lay out both options..."
```

Your test suite asserts equality.

**You cannot unit-test your way to confidence.**

---

## 2. It decides what to do at runtime

You did not write "call `check_room_availability` twice."

The model decided that. With arguments it chose.

**The control flow is not in your repository.**

---

## 3. Spend is a function of behaviour

A prompt change doubles token usage.

You find out on the invoice.

---

## 4. Tools are blast radius

A tool is a function that does something real.

Book a room. Issue a refund. Update a record.

**Every agent holding the same API key is one agent, wearing hats.**

---

## What this looks like in practice

| You have | You want |
|---|---|
| One `200 OK` per request | What happened inside it |
| Tests that pass regardless | A measure of whether it is any *good* |
| A key in an env var | An identity you can audit |
| An agent that works on a laptop | One that works on Tuesday, in production |

---

## Who feels this

**The agent developer** — "it worked in my notebook."

**The platform engineer** — "I now operate twenty of these."

**Security & compliance** — "which agent did that, for which customer?"

**The person signing it off** — "what does this cost, and what can it reach?"

Four jobs. Four different missing tools.

---

## The category: an agent control plane

The layer between *your agent code* and *everything it touches*.

| | |
|---|---|
| **Lifecycle** | build · deploy · promote · roll back |
| **Observability** | traces, tokens, tool calls |
| **Evaluation** | is it any good — continuously |
| **Governance** | model access, guardrails, spend |
| **Identity** | agents as principals, scoped tools |

---

## WSO2 Agent Manager

An open-source implementation of exactly that layer.

**Apache 2.0** · pre-1.0 and moving quickly

Built on OpenChoreo. OpenTelemetry GenAI semantics — not a proprietary
trace format.

Today we use the parts a developer meets first.

---

## One honest note

This is alpha software and we will treat it that way.

When something is rough, I will say so.

You will see at least one real failure today, on purpose.

---

## What we are going to do

```
00 — Baseline        An agent on a laptop. Works fine. Ships nowhere.
01 — Build & Deploy  Platform-hosted from Git. Console once, then CLI.
02 — Observability   Traces, and reading them without guessing.
03 — Evaluation      Measuring a thing that answers differently every time.
04 — External Agents The same laptop agent, governed without moving it.
```

github.com/a5anka/ai-lab-2026-africa-agent-manager

---

# Module 00

## An agent on a laptop

It works. The tests pass. Nothing is wrong with it.

---

## What module 00 showed

The answer was good.

The log was one line:

```
INFO:  127.0.0.1:52118 - "POST /chat HTTP/1.1" 200 OK
```

Two tool calls and several model calls happened inside it.

**None of them are visible. And it only runs here.**

---

# Module 01

## The agent leaves your laptop

Built from Git. No Dockerfile. No SDK. No code changes.

---

## What module 01 showed

**Build** from a repo path · **deploy** · **gateway** in front of it

The console for the first time — `amctl` for every time after

A green build that was **not** a running agent

And the platform handing your assistant the manual for its own CLI

---

# Next: Module 02

## Seeing inside a request

