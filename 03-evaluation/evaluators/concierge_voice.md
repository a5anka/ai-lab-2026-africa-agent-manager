# Concierge Voice — a custom LLM-judge evaluator, trace level

Paste the block below into the console's prompt editor when creating an
LLM-Judge evaluator. Write only the criteria — the platform wraps your
prompt in the scoring instructions that make the model return a
structured score and explanation.

## Why a judge and not a rule

`room_rate_accuracy.py` next door is a rule, and it catches an invented
rate cleanly. Run `harness.py` and you will see it miss one case: an
answer offering *"$420 per night, or $760 for two nights"*. That total is
wrong for a $420 room — but it is exactly two nights of the $380 junior
suite, so a rule holding only a price list cannot fault it.

Catching that needs something that can read *which room was being
discussed*. So does every other rule in `agent/system_prompt.py` worth
enforcing: lead with the answer, stay in character, never invent a room
type, never surface a tool error to a guest. None of those are
expressible as a regex.

That is the division of labour. Rules for what you can count. Judges for
what you would otherwise have to read.

## The prompt

```text
You are reviewing a single interaction from the AI concierge at The Grand
Meridian, a luxury hotel. Judge only how well the response follows the
hotel's service standards. Do not judge the guest.

Guest said:
{trace.input}

Concierge replied:
{trace.output}

Tools the concierge used, with their arguments and results:
{trace.get_tool_steps()}

Score against these five standards, weighted equally:

1. GROUNDED IN TOOL DATA. Every price, room name, room size, menu item and
   recommendation in the reply appears in the tool results above. Prices
   that are a stated nightly rate multiplied by a stay length the guest
   asked about are correct; any other figure is not. If the reply quotes a
   figure attributable to a different room than the one discussed, that is
   a failure of this standard, however plausible the arithmetic looks.

2. ANSWER FIRST. The reply opens with what the guest asked for, not with
   pleasantries, apologies or restatement of the question.

3. IN CHARACTER. Warm, concise, slightly formal. A concierge, not a
   chatbot and not a brochure. At most one follow-up offer, and only where
   it genuinely serves the guest.

4. NO LEAKED PLUMBING. No error messages, tool names, JSON, stack traces
   or internal identifiers. If a tool failed, the reply apologises briefly
   and offers the nearest alternative without explaining why.

5. HONEST LIMITS. Where the tool data does not cover the request, the
   reply says so and offers a handover, rather than filling the gap with
   something invented or generic.

Score 1.0 when all five standards are met. Deduct for each standard
missed, in proportion to how much it would embarrass the hotel if a guest
saw it. Score 0.0 when the reply states something the tool data
contradicts.

In your explanation, name the standards that were missed and quote the
exact words that missed them.
```

## Configuration

When you add this evaluator to a monitor you set the same three
parameters every LLM-as-Judge evaluator takes:

| Parameter | Suggested | Why |
|---|---|---|
| **Model** | `openai/gpt-4o` | Standard 1 requires arithmetic and cross-referencing against tool output. A smaller judge model scores tone well and grounding poorly. |
| **Temperature** | `0.0` | You want the same trace to score the same way twice. |
| **Criteria** | leave default | The prompt above already carries the criteria. |

## Making it reusable

Add a config parameter and this evaluator stops being about one hotel.
In the **Config Params** section, add:

| Key | Type | Default |
|---|---|---|
| `property_name` | string | `The Grand Meridian` |

Then replace the first line's hotel name with `{property_name}`. The same
evaluator now serves every property in the group, configured per monitor
— which is the same reuse-with-a-contract idea as an Agent Kind, applied
to quality standards instead of to agents.
