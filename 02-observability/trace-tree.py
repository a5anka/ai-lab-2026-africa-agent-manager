#!/usr/bin/env python3
"""Draw an `amctl` trace response as a span tree.

The console renders this tree for you. This is the same thing in the
terminal, for when you are already there — and for when you want to pipe
it somewhere.

Two inputs work, and they are not equivalent:

    # shape and timings only — this endpoint carries no attributes
    amctl agent trace grand-meridian-concierge <traceId> \
      --project default --env default --json | ./trace-tree.py

    # shape, timings AND token counts / tool arguments
    amctl agent traces export grand-meridian-concierge \
      --project default --env default --since 30m --limit 5 --json \
      | ./trace-tree.py

`traces export` is the one to reach for. `amctl agent trace` returns a
flat span list with names, kinds, parents and durations but no `gen_ai.*`
attributes — those are only on `traces export` and on single-span
lookups (`amctl agent trace ... --span <spanId>`).

Options:
    --attrs           print every gen_ai.* attribute on every span
    --trace <prefix>  with export input, render only this trace
    --tool-errors     skip the trees; list every tool call whose own
                      recorded output came back carrying an error

Standard library only. No dependencies, no install.
"""

from __future__ import annotations

import json
import sys

# The three endpoints spell the same fields differently — trace detail uses
# `spanName`/`spanKind`/`durationNs`, export and single-span lookups use
# `name`/`kind`/`durationInNanos`. Reading a small set of aliases keeps one
# script working across all of them.
NAME = ("name", "spanName", "operationName")
DURATION = ("durationInNanos", "durationNs", "durationNanos", "duration")

MODEL = "gen_ai.request.model"
TOK_IN = "gen_ai.usage.input_tokens"
TOK_OUT = "gen_ai.usage.output_tokens"


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


TOOL_OUTPUT = ("traceloop.entity.output", "gen_ai.tool.call.result")
TOOL_NAME = ("gen_ai.tool.name", "traceloop.entity.name")


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
    """Return the error message a tool reported, or "" if it reported none.

    A tool that returns {"error": ...} instead of raising leaves a span with
    a healthy status, so the platform counts the call as a success and
    --condition tool_call_fails will not match it. The evidence survives in
    the tool's own recorded output, which is what this reads.
    """
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


def report_tool_errors(found: list) -> int:
    """Print one line per failed tool call. Returns the number found."""
    hits = 0
    for trace_id, spans in found:
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
    return hits


def ms(nanos) -> float:
    try:
        return float(nanos) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


def traces_in(doc) -> list[tuple[str, list[dict]]]:
    """Return [(traceId, spans)] for either input shape."""
    data = doc.get("data", doc) if isinstance(doc, dict) else {}
    if isinstance(data.get("traces"), list):            # traces export
        return [(t.get("traceId", "?"), t.get("spans") or []) for t in data["traces"]]
    if isinstance(data.get("spans"), list):             # trace detail
        spans = data["spans"]
        tid = spans[0].get("traceId", "") if spans else ""
        return [(tid, spans)]
    sys.exit("Could not find spans in that JSON. Pipe in `amctl agent trace "
             "<agent> <traceId> --json` or `amctl agent traces export ... --json`.")


def render_trace(trace_id: str, spans: list[dict], show_attrs: bool) -> None:
    children: dict[str, list[dict]] = {}
    roots: list[dict] = []
    ids = {s.get("spanId") for s in spans}
    for s in spans:
        parent = s.get("parentSpanId")
        (children.setdefault(parent, []) if parent in ids else roots).append(s)
    for kids in children.values():
        kids.sort(key=lambda s: str(s.get("startTime", "")))
    roots.sort(key=lambda s: str(s.get("startTime", "")))

    longest = max((ms(pick(s, DURATION, 0)) for s in spans), default=0.0) or 1.0
    llm = [s for s in spans if kind_of(s) == "llm"]
    tools = [s for s in spans if kind_of(s) == "tool"]
    tok_in = sum(int(attrs_of(s).get(TOK_IN, 0) or 0) for s in llm)
    tok_out = sum(int(attrs_of(s).get(TOK_OUT, 0) or 0) for s in llm)

    def plural(n: int, word: str) -> str:
        return f"{n} {word}" + ("" if n == 1 else "s")

    header = (f"{trace_id[:8] + '  ' if trace_id else ''}"
              f"{plural(len(spans), 'span')} · {plural(len(llm), 'model call')} "
              f"· {plural(len(tools), 'tool call')}")
    if tok_in or tok_out:
        header += f" · {tok_in:,} in / {tok_out:,} out tokens"
    print(header)
    print()

    def walk(span: dict, depth: int = 0) -> None:
        a = attrs_of(span)
        dur = ms(pick(span, DURATION, 0))
        bar = "█" * max(1, round(24 * dur / longest)) if dur else ""
        label = f"{'  ' * depth}{pick(span, NAME, '(unnamed)')}"
        line = f"{label:<50.50}{dur:>8,.0f}ms  {bar}"
        if MODEL in a:
            line += f"   {a[MODEL]}  {a.get(TOK_IN, '?')} in / {a.get(TOK_OUT, '?')} out"
        elif kind_of(span) == "tool" and tool_args(span):
            line += f"   {tool_args(span)[:60]}"
        print(line)
        if show_attrs:
            for k in sorted(k for k in a if k.startswith("gen_ai.")):
                print(f"{'  ' * depth}    {k} = {str(a[k])[:110]}")
        for kid in children.get(span.get("spanId"), []):
            walk(kid, depth + 1)

    for root in roots:
        walk(root)


def main() -> None:
    argv = sys.argv[1:]
    show_attrs = "--attrs" in argv
    tool_errors = "--tool-errors" in argv
    wanted = argv[argv.index("--trace") + 1] if "--trace" in argv else None

    try:
        doc = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.exit(f"Not JSON on stdin: {exc}")
    if isinstance(doc, dict) and doc.get("error"):
        sys.exit(f"amctl returned an error: {doc['error'].get('message', doc['error'])}")

    found = traces_in(doc)
    if wanted:
        found = [t for t in found if t[0].startswith(wanted)]
        if not found:
            sys.exit(f"No trace starting with {wanted!r} in that input.")

    if tool_errors:
        report_tool_errors(found)
        return

    for i, (trace_id, spans) in enumerate(found):
        if i:
            print()
        render_trace(trace_id, spans, show_attrs)


if __name__ == "__main__":
    main()
