#!/usr/bin/env python3
"""List every tool call whose own recorded output came back carrying an error.

A tool that returns {"error": ...} instead of raising leaves a span with a
healthy status. The function completed, so `errorCount` is 0 and
`--condition tool_call_fails` does not match — all of which is correct,
because that is what the code reported. The evidence survives anyway: the
tool's arguments and its result are both recorded on the span, which is
what this reads.

    amctl agent traces export grand-meridian-concierge \
      --project default --env default --since 24h --limit 100 --json \
      | ./tool-errors.py

    dd45e286  check_room_availability
              reported: Nights must be an integer between 1 and 30.
              called with: {"check_in":"2026-11-01","nights":45,...}

Use `amctl agent traces export`. The single-trace endpoint
(`amctl agent trace <traceId>`) returns a flat span list with no
attributes, so there is nothing for this to read — it is accepted, and
will simply find nothing.

For the shape of a request — the span tree, timings, token counts per
model call — use the console's Traces view. It draws that better than a
terminal can.

Standard library only. No dependencies, no install.
"""

from __future__ import annotations

import json
import sys

NAME = ("name", "spanName", "operationName")
TOOL_OUTPUT = ("traceloop.entity.output", "gen_ai.tool.call.result")
TOOL_NAME = ("gen_ai.tool.name", "traceloop.entity.name")


def pick(obj: dict, keys: tuple[str, ...], default=None):
    for k in keys:
        if obj.get(k) not in (None, ""):
            return obj[k]
    return default


def kind_of(span: dict) -> str:
    amp = span.get("ampAttributes") or {}
    return amp.get("kind") or span.get("spanKind") or span.get("kind") or ""


def attrs_of(span: dict) -> dict:
    raw = span.get("attributes") or {}
    return raw if isinstance(raw, dict) else {}


def tool_args(span: dict) -> str:
    amp = span.get("ampAttributes") or {}
    val = amp.get("input")
    return val if isinstance(val, str) else ""


def tool_output(span: dict) -> str:
    a = attrs_of(span)
    for k in TOOL_OUTPUT:
        v = a.get(k)
        if isinstance(v, str) and v:
            return v
    amp = span.get("ampAttributes") or {}
    v = amp.get("output")
    return v if isinstance(v, str) else ""


def error_in_output(text: str) -> str:
    """Return the error message a tool reported, or "" if it reported none."""
    if not text:
        return ""
    for needle in ('\\"error\\":', '"error":', "'error':"):
        i = text.find(needle)
        if i == -1:
            continue
        tail = text[i + len(needle):].lstrip()
        for quote in ('\\"', '"', "'"):
            if tail.startswith(quote):
                rest = tail[len(quote):]
                end = rest.find(quote)
                if end > 0:
                    return rest[:end]
        return tail[:120].rstrip(",}").strip()
    return ""


def traces_in(doc) -> list[tuple[str, list[dict]]]:
    """Return [(traceId, spans)] for either input shape."""
    data = doc.get("data", doc) if isinstance(doc, dict) else {}
    if isinstance(data.get("traces"), list):            # traces export
        return [(t.get("traceId", "?"), t.get("spans") or []) for t in data["traces"]]
    if isinstance(data.get("spans"), list):             # trace detail
        spans = data["spans"]
        tid = spans[0].get("traceId", "") if spans else ""
        return [(tid, spans)]
    sys.exit("Could not find spans in that JSON. Pipe in "
             "`amctl agent traces export <agent> ... --json`.")


def main() -> None:
    try:
        doc = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.exit(f"Not JSON on stdin: {exc}")
    if isinstance(doc, dict) and doc.get("error"):
        sys.exit(f"amctl returned an error: {doc['error'].get('message', doc['error'])}")

    hits = 0
    for trace_id, spans in traces_in(doc):
        for span in spans:
            if kind_of(span) != "tool":
                continue
            message = error_in_output(tool_output(span))
            if not message:
                continue
            hits += 1
            name = pick(attrs_of(span), TOOL_NAME, pick(span, NAME, "?"))
            print(f"{trace_id[:8]}  {name}")
            print(f"          reported: {message}")
            args = tool_args(span)
            if args:
                print(f"          called with: {args[:160]}")

    if not hits:
        print("No tool call in this window reported an error.")


if __name__ == "__main__":
    main()
