# Module 01 — Build & Deploy: source in, service out

**Duration:** 15 min

Register the agent as a **Platform-Hosted Agent**, built straight from
this Git repository. Agent Manager clones the repo, builds an image with
a buildpack, deploys it, and puts a gateway in front of it.

The agent code does not change. Nothing is added to it — no Dockerfile,
no manifest, no SDK.

> The terminal steps below use `amctl` — install it and log in first, as
> described in the [repo README](../README.md#prerequisites). On the
> hosted version, follow the console route in each step; `amctl` and the
> MCP servers talk to a self-managed install today.

## Step 1 — Register it in the console

1. Open your project and click **Add Agent**.
2. Pick **Platform-Hosted Agent**, then **Connect a Git repository**.
3. Fill in the source:

   | Field | Value |
   |---|---|
   | Repository URL | `https://github.com/wso2con/2026-NBO-AI-tutorial-3` |
   | Branch | `main` |
   | Application path | `/agent` |

4. Agent type **Chat Agent**, build type **Buildpack**, language
   **Python**, version **3.11**, run command `python main.py`.
5. Environment variables:

   | Key | Value | Secret |
   |---|---|---|
   | `OPENAI_API_KEY` | your key | ✅ |
   | `OPENAI_MODEL` | `gpt-4o` | |
   | `PORT` | `8000` | |

   **`PORT` is not optional.** See "Why `PORT`" below — it is the single
   most common reason a lab agent builds fine and never comes up.

6. Click **Create**. The build starts automatically.

## Step 2 — Watch the build

The first build takes **five to ten minutes** — the buildpack resolves
and compiles every dependency in `requirements.txt`, and LangGraph pulls
a lot of them. Subsequent deploys of the same image take seconds.

Watch it from the console's **Build** tab, or from the terminal:

```bash
amctl agent build list grand-meridian-concierge --project default --json \
  | jq -r '.data.builds[0] | "\(.buildName)  \(.status)  \(.percent // 0)%"'
# → grand-meridian-concierge-1789202170069  Running  50%
# → grand-meridian-concierge-1789202170069  Completed  0%
```

(`percent` comes back `null` once a build finishes, hence the `// 0` —
read `status`, not the number, to know when it is done.)

Builds are addressed by `buildName` — the long
`grand-meridian-concierge-1789202170069` form — not by the `buildId`
UUID sitting next to it. The UUID is accepted by nothing.

## Step 3 — Confirm it is actually running

When the build reports `Completed`, the agent is not necessarily up.
Those are two different claims, and only one of them has been made.

```bash
amctl agent status grand-meridian-concierge --project default --json \
  | jq '.data.environments[] | {name, status, url: .endpoints[0].url}'
```

Wait for `"status": "active"`. Note the endpoint URL — you need it next.
The console shows the same thing on the agent's overview: each
environment with its own status and endpoint.

`amctl agent get` will *not* tell you this. Its `status` field is empty
even when the agent is broken. Liveness comes from `status`, `logs` or
`metrics`, never from `get`.

> **"Deployed" does not mean "in production."**
>
> Deploying places the agent in the **lowest environment** of its
> deployment pipeline — `default` here. The CLI is blunt about it:
> *"Deploy a built agent image to the lowest environment in the deployment
> pipeline."* There is no target-environment flag.
>
> Getting to production is a separate, deliberate step: you **promote** the
> same built image up the pipeline, picking up each environment's own
> configuration on the way. Promotion is a console action — there is no
> `amctl promote`.
>
> So the shape is *build once, deploy to dev, test there, promote onward* —
> not push-to-prod. This lab uses a single environment, so there is nothing
> to promote to; environments and promotion are a session-2 topic.

## Step 4 — Call it

Deployed agents sit behind the gateway with API-key authentication on by
default. Without a key:

```bash
curl -s -X POST "$AGENT_URL/chat" -H 'Content-Type: application/json' \
  -d '{"message":"What are the pool hours?","session_id":"lab-1","context":{}}'
# → {"error":"Unauthorized","message":"Valid API key required"}
```

Create a key — in the console under the agent's environment settings, or:

```bash
amctl api --project default \
  '/orgs/{org}/projects/{project}/agents/grand-meridian-concierge/environments/default/api-keys' \
  -f name=lab-key
# → {"status":"success", "keyId":"lab-key", "apiKey":"75f738d2...", "gatewayConnected":true}
```

Then the same call, with the key:

```bash
curl -s -X POST "$AGENT_URL/chat" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_KEY" \
  -d '{"message":"What are the pool hours?","session_id":"lab-1","context":{}}'
# → {"response":"The pool is open 7am-10pm daily. ..."}
```

The same agent you ran locally in module 00, now behind a gateway
that will not talk to a stranger.

## Step 5 — The same thing, in one command

The console is for the first time. This is for every time after:

```bash
amctl agent create grand-meridian-concierge \
  --project default \
  --display-name "Grand Meridian Concierge" \
  --subtype chat-api \
  --build-type buildpack \
  --language python --language-version 3.11 \
  --run-command "python main.py" \
  --repo-url https://github.com/wso2con/2026-NBO-AI-tutorial-3 \
  --repo-branch main --repo-path /agent \
  --env OPENAI_MODEL=gpt-4o \
  --env PORT=8000 \
  --env-secret OPENAI_API_KEY=sk-... \
  --json
```

One call creates the agent, starts the build, and deploys it when the
build completes.

> **Secrets:** `--env-secret` stores the value as a secret at create
> time. `amctl agent deploy --env` does **not** — values passed there are
> stored as plain text. Set real secrets at create time or in the
> console.

There is also a declarative form, which is what you would actually commit:

```bash
amctl agent create --template > agent.yaml   # then edit
amctl agent create -f agent.yaml
```

## Step 6 — Hand the CLI to your assistant

Agent Manager publishes skills that teach an AI coding assistant how to
drive `amctl` properly:

```bash
amctl skills list
# → manage-agent (not installed)  Use when an agent needs to drive the full
#   agent-manager lifecycle through `amctl` ...

amctl skills install
```

It installs to `~/.agents/skills/` and links itself into the assistants
it finds. Claude Code picks it up in the same session — no restart.

What you just installed is not a wrapper or a plugin. It is written
guidance: the verb map, the rules that stop calls failing silently, a
`troubleshooting.md` of the CLI's sharp edges, and a `triage.md` for
exactly the "build completed but is it running?" question from step 3.

Now ask, in plain English:

> *"Is the Grand Meridian concierge actually serving traffic?"*

and the assistant runs the build → logs → metrics → traces sequence
rather than guessing.

## Why `PORT`

Worth understanding, because the failure is silent and the logs only make
sense once you have seen it.

Chat Agents are expected on port **8000**. But the Python buildpack sets
its own conventional `PORT=8080` in the container, and `agent/main.py`
does what any well-behaved twelve-factor app does — it honours `PORT`:

```python
port = int(os.environ.get("PORT", "8000"))
```

So the app binds 8080, nothing answers on 8000, the health check fails,
and the pod is torn down and restarted. The build is green throughout.
The runtime logs tell the whole story:

```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
INFO:     Application startup complete.
INFO:     Shutting down                          ← health check never passed
```

Setting `PORT=8000` explicitly overrides the buildpack default:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

and the status flips to `active`.

If you ever hit this without knowing the cause:

```bash
amctl agent logs grand-meridian-concierge --project default --env default \
  --since 30m --json | jq -r '.data.logs[] | "\(.timestamp) \(.log)"'
```

`Uvicorn running on ...` followed by `Shutting down`, on a loop, is the
signature.

## Going further

- [`amctl` reference](https://wso2.github.io/agent-manager/docs/) — and `amctl <command> --help`, which is always more current than any document
- [Cloud Native Buildpacks](https://buildpacks.io/)

---

Previous: [Module 00 — Starting Point](../00-starting-point/README.md) ·
Next: [Module 02 — Observability](../02-observability/README.md)
