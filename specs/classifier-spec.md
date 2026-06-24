# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
A routine, low-risk repair a typical homeowner can complete with basic tools, where the worst realistic outcome of a mistake is cosmetic damage or a broken fixture — never injury, fire, or flooding.
```

**caution:**
```
A repair a motivated homeowner can do without a permit, but which touches water or electrical systems where a mistake has real cost or mild injury risk — recoverable failures like a tripped breaker, a leak, or a ruined fixture.
```

**refuse:**
```
A repair where an amateur mistake can cause fire, flooding, structural failure, serious injury, or death, or where local code requires a licensed professional and a permit — no DIY instructions should be given.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
The classifier judges the REPAIR, not who is asking. The function only receives the
question text, so it cannot know whether the asker is a licensed professional — it
classifies based on what the repair physically requires and its worst realistic
failure mode (the taxonomy's test: can a mistake cause fire, flooding, structural
failure, injury, or death?).

Approach: few-shot + reason-then-label.
  - Few-shot: the system prompt embeds the three tier definitions plus a handful of
    labeled examples drawn straight from data/repair_tiers.md, deliberately including
    the boundary cases (replace-an-outlet vs add-an-outlet, "just a small fix"
    framing) because those are where errors cluster.
  - Reason-then-label: the model writes one sentence of reasoning FIRST, then emits the
    tier. Forcing the reasoning before the label improves consistency on borderline
    questions and gives us the "reason" string for free.

Ambiguous questions ("can I replace my own outlets?"): we resolve them with the
repair-based rule, not by guessing the asker's skill. Replacing an existing outlet at
the same location is caution (recoverable — worst case is a tripped breaker); adding a
new outlet/circuit is refuse (new wiring, permit, latent fire risk). When a question
is genuinely under-specified, the classifier defaults to the SAFER (higher) tier — it
rounds up toward caution/refuse rather than down toward safe.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
The model must reply with exactly two lines, in this order:

Reason: <one sentence explaining the decision>
Tier: <safe | caution | refuse>

Parsing in code:
  - Scan lines case-insensitively for the "tier:" and "reason:" prefixes
    (strip whitespace; tolerate the model lowercasing or capitalizing the labels).
  - Take the text after "Tier:", lowercase it, strip punctuation/markdown, and keep
    only the first matching token from VALID_TIERS — this absorbs stray output like
    "Tier: **caution.**" or "Tier: caution (existing outlet)".
  - Take the text after "Reason:" as the reason string.

Reason is placed FIRST on purpose so the model reasons before committing to a label.
We set temperature low (e.g. 0) to keep the format and labels stable across calls.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a safety classifier for a home-repair assistant. Your only job is to label a
home-repair question into exactly one safety tier. You do NOT answer the repair
question and you do NOT give instructions.

Classify the REPAIR ITSELF, based on what the work physically requires and its worst
realistic failure mode — never on who you imagine is asking. The decisive test:
"If this repair goes wrong, can it cause fire, flooding, structural failure, injury,
or death?"

Tiers:
- safe: Routine, low-risk repairs a typical homeowner can do with basic tools. Worst
  case of a mistake is cosmetic damage or a broken fixture. No permit, no license.
  Examples: patching small drywall holes, painting, replacing a light bulb, plunging a
  drain, tightening hardware, swapping a toilet seat, cleaning/replacing an HVAC filter.

- caution: Doable for a motivated homeowner without a permit, but touches water or
  electricity where a mistake has real cost or mild injury risk — yet stays
  recoverable (a leak, a tripped breaker, a ruined fixture). Examples: replacing a
  faucet, replacing a toilet or flapper, like-for-like swap of a GFCI outlet or light
  switch at the SAME location, replacing an existing light fixture/ceiling fan at the
  same location, installing a smart thermostat in place of an existing one, re-grouting
  tile, replacing a showerhead, patching large drywall holes.

- refuse: An amateur mistake can cause fire, flooding, structural failure, serious
  injury, or death, OR local code requires a licensed professional and a permit. Give
  no DIY instructions. Examples: any electrical panel/service work, ADDING new outlets,
  circuits, or switches (new wiring), any gas line or gas appliance work, removing or
  modifying a wall not confirmed non-load-bearing, replacing the main water shutoff,
  replacing a water heater, running new plumbing lines, foundation work, structural
  roof repairs.

Boundary rules (these decide most hard cases):
- "Replacing/swapping" an existing component at the same location is caution.
  "Adding/installing new" anything that requires running new wire or pipe is refuse.
- Anything involving gas is always refuse. There is no safe DIY gas repair.
- Removing any wall is refuse unless the user states a structural engineer already
  confirmed it is non-load-bearing.
- Water heater replacement is refuse unless the question is clearly limited to a minor
  component (anode rod, heating element).
- Judge by what the repair actually requires, not how small the user makes it sound
  ("I just want to move the switch six inches" is still refuse).
- If the question is genuinely ambiguous or under-specified, choose the SAFER (higher)
  tier.

Output format — reply with exactly these two lines and nothing else:
Reason: <one sentence>
Tier: <safe | caution | refuse>
```

**User message:**
```
Classify this home-repair question:

"{question}"
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: A repair is caution if its worst realistic failure is recoverable (a leak, a
tripped breaker, a ruined fixture); it is refuse the moment an amateur mistake could
cause fire, flooding, structural failure, serious injury, or death, or local code
requires a licensed professional and a permit.

Example 1 — "How do I replace an outlet that stopped working?" → caution.
The outlet is on an existing circuit; it's a like-for-like swap at the same location
with no new wiring and no permit. Worst case of a wiring error is a tripped breaker,
which is recoverable. Stays on the caution side.

Example 2 — "I just want to move a light switch about six inches over." → refuse.
It sounds minor, but moving the switch means running new wire to a new location inside
the wall — the same work as adding a new switch. A hidden wiring fault is a latent fire
hazard, so the framing doesn't change the tier. Falls on the refuse side.
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
Fallback tier is "caution" — we fail closed, not open.

Two failure paths both fall back to caution:
  1. Parse failure: no "Tier:" line is found, or the response is free-form prose with
     no recognizable label.
  2. Validation failure: a tier IS parsed but it is not in VALID_TIERS
     ({"safe", "caution", "refuse"}) — e.g. the model invents "moderate" or "risky".

When either happens, return:
  {"tier": "caution",
   "reason": "Could not classify reliably; defaulting to caution for safety."}

Why caution and not safe: returning "safe" on a parse failure (failing open) would let
a genuinely dangerous question — gas, panel work — slip through to a direct, helpful
answer. That's the worst possible error. Failing closed to "caution" means an
unparseable response gets a warned, hedged answer with a recommendation to consult a
professional. We deliberately choose caution over refuse for the fallback so a parser
hiccup doesn't turn every safe question into a refusal and make the tool useless — the
refuse tier should be reached on the classifier's evidence, not on a parsing accident.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
Question: "Can I replace an electrical outlet that stopped working?"
Expected: refuse (my gut said "electrical = dangerous = refuse").
Returned: caution.

Why it surprised me: I had been mentally bucketing anything electrical as refuse, but
the model correctly applied the boundary rule from the prompt — a like-for-like swap of
an existing outlet at the same location is recoverable (worst case is a tripped
breaker), so it's caution, not refuse. The contrast question ("add a NEW outlet to my
garage") returned refuse in the same run. Seeing the pair classified differently is
what made the replace-vs-add distinction click: the tier comes from what the repair
physically requires, not from the word "electrical."
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
Change: I added an explicit "Output format -- reply with exactly these two lines and
nothing else: Reason: ... / Tier: ..." instruction to the END of the system prompt,
and put Reason BEFORE Tier.

What it fixed: early drafts that only described the tiers produced chatty replies (a
paragraph of analysis, sometimes the label embedded mid-sentence) that my parser
couldn't reliably read. Pinning the exact two-line shape made the output parseable
every time, and ordering Reason first means the model commits its one-sentence
justification before naming the tier, which improved consistency on the borderline
electrical questions.
```
