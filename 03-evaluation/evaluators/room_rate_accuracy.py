# Room Rate Accuracy — a custom code evaluator, trace level.
#
# Checks that every money figure in the agent's answer can be accounted
# for by the hotel's real price list: either a published price, or a
# published price multiplied by a night count.
#
# This is the check no built-in evaluator can do for you, because only you
# know what your rooms cost. It is also the failure that worries people
# most — a confident, well-written, fast, cheap answer quoting a rate the
# hotel does not charge.
#
# Config parameters (set when you add the evaluator to a monitor):
#   valid_amounts  array   the published prices, e.g. [280, 340, 380, 420, 1200]
#   max_nights     integer largest multiple to accept as a total (default 30)
#
# Everything between the two markers is what you paste into the console's
# code editor. The console supplies the imports and the signature header.

# --- paste from here -------------------------------------------------
def evaluate(trace: Trace, valid_amounts: list = None, max_nights: int = 30) -> EvalResult:
    import re

    if not trace.output:
        return EvalResult.skip("No output to evaluate")

    if not valid_amounts:
        return EvalResult.skip(
            "No valid_amounts configured. Add the published prices to this "
            "evaluator's configuration."
        )

    text = trace.output

    # $1,140  ·  1140 USD  ·  USD 1,140
    money = re.findall(
        r"\$\s*([\d,]+(?:\.\d{2})?)"
        r"|([\d,]+(?:\.\d{2})?)\s*(?:USD|usd|dollars)"
        r"|(?:USD|usd)\s*([\d,]+(?:\.\d{2})?)",
        text,
    )
    amounts = []
    for groups in money:
        raw = next((g for g in groups if g), None)
        if raw:
            try:
                amounts.append(float(raw.replace(",", "")))
            except ValueError:
                pass

    if not amounts:
        return EvalResult.skip("No money figures in the response")

    # A total is only legitimate for a stay length the conversation actually
    # mentions. Without this, almost any number is "some price times some
    # number of nights" and the check passes everything.
    WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    haystack = f"{trace.input or ''} {text}".lower()
    nights = {1}
    for match in re.findall(r"(\d{1,2}|" + "|".join(WORDS) + r")[\s-]*nights?", haystack):
        count = WORDS.get(match) or int(match)
        if 1 <= count <= max_nights:
            nights.add(count)

    unit_prices = {float(a) for a in valid_amounts}
    grounded = {p * n for p in unit_prices for n in nights}

    ok, unaccounted = [], []
    for amount in amounts:
        (ok if amount in grounded else unaccounted).append(amount)

    score = len(ok) / len(amounts)
    one = len(amounts) == 1
    noun, verb = ("figure", "matches") if one else ("figures", "match")

    if not unaccounted:
        return EvalResult(
            score=1.0,
            explanation=f"All {len(amounts)} money {noun} {verb} the published "
                        f"price list, or a nightly multiple of it.",
        )

    shown = ", ".join(f"${a:,.0f}" for a in sorted(set(unaccounted))[:5])
    return EvalResult(
        score=score,
        explanation=f"{len(unaccounted)} of {len(amounts)} money {noun} not "
                    f"on the price list, and not a multiple of it for any "
                    f"stay length mentioned: {shown}. Published prices: "
                    f"{sorted(int(p) for p in unit_prices)}; nights referenced: "
                    f"{sorted(nights)}.",
    )
# --- to here ---------------------------------------------------------
