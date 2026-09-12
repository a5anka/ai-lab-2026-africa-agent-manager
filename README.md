# Running Agents Like Production Software

**WSO2Con 2026 Africa — Agent Manager lab, session 1**

Your agent works on your laptop. This lab is about everything that
happens after that: getting it built, deployed, instrumented, and
measured — using [WSO2 Agent Manager](https://wso2.com/agent-platform/agent-manager/).

## Tutorial plan

```
00 — Baseline        An agent on a laptop. Works fine. Ships nowhere.
01 — Build & Deploy  Platform-hosted from Git. Console once, then amctl.
02 — Observability   OTEL GenAI traces, and reading them without guessing.
03 — Evaluation      You cannot unit-test a thing that answers differently every time.
04 — External Agents The same laptop agent, governed without moving it.
```

Each module has its own `README.md` with the steps. They are written to be
followed in order — later modules assume the agent registered in 01.

The opening talk is in [`slides.md`](slides.md).

## The use case

A concierge agent for *The Grand Meridian*, a fictional luxury hotel.
LangGraph + FastAPI + OpenAI, roughly 300 lines. One endpoint:

```
POST /chat   { "message": str, "session_id": str, "context": {} }
         →   { "response": str }
```

Three tools, backed by static hotel data:

- `check_room_availability(room_type, check_in, nights)`
- `get_room_service_menu(vegetarian_only)`
- `get_local_recommendations(category)`

The agent lives in [`agent/`](agent/) and is **shared by every module** —
one copy, never edited as you go. That is the point of the lab: the
architecture around the agent changes at every step while the agent
itself stays exactly as it was written.

## Prerequisites

- **Python 3.11 or 3.12.** Avoid 3.13 / 3.14 — the LangGraph pins used
  here do not support them yet. macOS: `brew install python@3.11`.
- **An OpenAI API key** (`sk-...`).
- **An Agent Manager instance** you can register an agent in. The fastest
  path is the hosted version at
  [console.agent-manager.cloud.wso2.com](https://console.agent-manager.cloud.wso2.com).
  Module 00 runs without one; modules 01–04 need it.
- **`amctl`**, the Agent Manager CLI — installed in module 01, not before.

## Quick start

```bash
git clone <repo-url> ai-lab-2026-africa
cd ai-lab-2026-africa/agent

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — paste your OPENAI_API_KEY
set -a; source .env; set +a

python main.py
# → listening on http://localhost:8000
```

Then open [`00-baseline/README.md`](00-baseline/README.md).

## A note on versions

Agent Manager is pre-1.0 and moving quickly. This lab was built and
verified against `amctl 1.0.0-alpha1`. Flags and screens may have shifted
by the time you read this — `amctl <command> --help` is always the
authority on flag shape, not this repo.

## Licence

Apache 2.0.
