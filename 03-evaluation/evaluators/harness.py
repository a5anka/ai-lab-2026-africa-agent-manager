#!/usr/bin/env python3
"""Run a custom code evaluator locally, before pasting it into the console.

    ./harness.py room_rate_accuracy.py

Custom evaluators are written and saved in the AMP Console. That is a slow
loop to debug in: save, open a monitor, wait for a run, read the score.
This runs the same function against sample traces on your machine, in
about a second.

It defines the two objects AMP injects for you — `Trace` and `EvalResult`
— with the same surface the real ones expose at trace level, then execs
the block between the `paste from here` / `to here` markers in your
evaluator file and calls it.

It is a development aid, not a reimplementation of the evaluation engine.
The score you see here is the score that function will produce; the
plumbing around it is AMP's.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass
class EvalResult:
    score: float = 0.0
    explanation: str = ""
    skipped: bool = False

    @classmethod
    def skip(cls, reason: str) -> "EvalResult":
        return cls(score=0.0, explanation=reason, skipped=True)

    def render(self) -> str:
        if self.skipped:
            return f"SKIP    —     {self.explanation}"
        return f"{self.score:>5.0%}   {self.explanation}"


@dataclass
class Trace:
    """The trace-level object an evaluator receives."""
    input: str = ""
    output: str = ""
    tool_steps: list = field(default_factory=list)

    def get_tool_steps(self) -> list:
        return self.tool_steps


# Real answers from the deployed concierge, plus two that never happened —
# the point of the evaluator is to tell them apart.
CASES = [
    ("real · one room",
     Trace(input="What does a deluxe room cost?",
           output="A deluxe room costs $340 per night. It features a separate "
                  "sitting area, a soaking tub, and a full harbor view.")),

    ("real · a 3-night total",
     Trace(input="Compare a junior suite and the presidential suite for a 3-night stay.",
           output="The Junior Suite covers 540 square feet. For a 3-night stay, "
                  "the total is $1,140. The Presidential Suite is $3,600 for "
                  "the same three nights.")),

    ("real · no prices at all",
     Trace(input="What are the pool hours?",
           output="The pool is open 7am-10pm daily.")),

    ("caught · a rate we do not charge",
     Trace(input="What does the garden suite cost?",
           output="The Garden Suite is $295 per night, with a private patio "
                  "and courtyard view.")),

    ("missed · plausible arithmetic, wrong room",
     Trace(input="Any deal on the honeymoon suite for two nights?",
           output="I can offer the Honeymoon Suite at $420 per night, or $760 "
                  "for two nights as a seasonal rate.")),
]

# Matches agent/hotel_data.py
CONFIG = {"valid_amounts": [280, 340, 380, 420, 1200]}


def load(path: str):
    src = open(path).read()
    try:
        body = src.split("# --- paste from here")[1].split("# --- to here")[0]
    except IndexError:
        sys.exit(f"{path}: expected '# --- paste from here' and '# --- to here' markers.")
    body = body.split("\n", 1)[1]
    scope = {"Trace": Trace, "EvalResult": EvalResult}
    exec(compile(body, path, "exec"), scope)
    if "evaluate" not in scope:
        sys.exit(f"{path}: no `evaluate` function between the markers.")
    return scope["evaluate"]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "room_rate_accuracy.py"
    evaluate = load(path)
    print(f"{path}   ·   {len(CASES)} sample traces\n")
    for label, trace in CASES:
        try:
            result = evaluate(trace, **CONFIG)
        except Exception as exc:                      # noqa: BLE001
            print(f"{label:<38} ERROR   {type(exc).__name__}: {exc}")
            continue
        print(f"{label:<38} {result.render()}")
    print()
    print("The first three are real answers from the deployed agent and score")
    print("as they should. The fourth invents a rate and is caught.")
    print()
    print("The fifth is the interesting one. $760 for two nights of a $420")
    print("room is wrong — but it is exactly two nights of the $380 junior")
    print("suite, so a rule that only knows the price list cannot fault it.")
    print("Catching that needs a judge that can read which room was being")
    print("discussed. That is what concierge_voice.md and the built-in")
    print("Groundedness evaluator are for.")


if __name__ == "__main__":
    main()
