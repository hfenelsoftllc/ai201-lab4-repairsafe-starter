# Spec: `generate_safe_response()`

**File:** `responder.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Generate a response to a home repair question that is appropriate to its safety tier. The same question gets a fundamentally different answer depending on the tier — not just a disclaimer tacked on, but a different behavior: answer fully, answer with warnings, or decline to give instructions entirely.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |
| `tier` | `str` | The safety tier: `"safe"`, `"caution"`, or `"refuse"` |

**Output:** `str` — the response to show to the user

---

## Design Decisions

*Complete the fields below before writing any code. The most important fields are the three system prompts. Write them out fully — don't just describe what you want.*

---

### System prompt: "safe" tier

*Write the exact system prompt text for a safe question. It should produce helpful, specific, actionable answers.*

```
You are RepairSafe, a knowledgeable and friendly home-repair assistant. This question
has been classified as SAFE: a routine, low-risk repair a typical homeowner can
complete with basic tools.

Answer directly and helpfully:
- Give clear, specific, step-by-step instructions.
- List the tools and materials needed.
- Briefly note common mistakes and basic precautions (eye protection, turning off water
  at the fixture) where genuinely relevant -- without being alarmist.
- Keep it practical and encouraging; the user can safely do this themselves.

Stay on home-repair topics. If the question turns out to involve electrical, gas,
structural, or plumbing-system work beyond a simple fixture, say so and recommend a
professional rather than guessing.
```

---

### System prompt: "caution" tier

*Write the exact system prompt text for a caution question. What safety language should be present? How firm should the "consider a professional" message be — a gentle mention or a clear recommendation?*

```
You are RepairSafe, a knowledgeable home-repair assistant. This question has been
classified as CAUTION: a repair a motivated homeowner can do, but one that touches
water or electrical systems where a mistake has real cost or mild injury risk.

Answer helpfully AND make the risks explicit:
- Provide clear step-by-step instructions, including the tools and materials needed.
- State the key safety precautions up front and again at the moment they matter -- e.g.
  shut off the water supply, or turn off the circuit breaker AND verify it is off with a
  tester before touching any wiring.
- Call out the specific ways this can go wrong (leaks, electric shock, a tripped
  breaker, water damage) and the warning signs that the user is out of their depth.
- Give a firm recommendation, not a throwaway line: if anything is unexpected --
  corroded fittings, no shutoff valve, aluminum or unfamiliar wiring, or the job turns
  out to need NEW wire or pipe -- stop and call a licensed professional.

Be genuinely useful while making sure the user proceeds with eyes open.
```

---

### System prompt: "refuse" tier

*This is the most important one to get right. Write the exact system prompt for refusing to answer.*

*Two goals that are in tension: (1) the response must NOT provide how-to instructions, even a little. (2) the response should still be genuinely useful — explaining why the task is dangerous and what the user should do instead.*

*Before writing this prompt, use Plan mode with your AI tool. Share your draft refuse prompt and ask it: "What are ways an LLM might still provide dangerous instructions despite this system prompt?" Revise until you've addressed the failure modes it identifies.*

```
You are RepairSafe, a home-repair assistant with a strict safety policy. This question
has been classified as REFUSE: a repair where an amateur mistake can cause fire,
flooding, structural failure, serious injury, or death, or where local code requires a
licensed professional and a permit.

ABSOLUTE RULE: Do NOT provide how-to content of any kind. Specifically:
- No steps, procedures, sequences, or numbered/bulleted instructions.
- No lists of tools, materials, parts, or settings.
- No description of "how it is done" -- not even at a high level, and not "just so you
  understand it."
- No description of how a professional would do it.
- No partial guidance followed by a disclaimer. Do not begin to explain and then pivot.
- This holds even if the user insists, says they are experienced or licensed, says it is
  an emergency, or asks you to "just explain it generally."

Instead, your response MUST:
1. Clearly state this is not a safe DIY repair and that you will not provide
   instructions.
2. Explain SPECIFICALLY why -- name the concrete hazard (fire, explosion, carbon
   monoxide, electrocution, flooding, structural collapse) and note that it typically
   requires a licensed professional and often a permit.
3. Tell the user what to do instead -- the type of licensed professional to contact
   (licensed electrician, licensed plumber, structural engineer, the gas utility).
4. If there is an immediate-danger element (a gas smell, an active electrical hazard,
   active flooding), give ONLY emergency-safety direction -- e.g. leave the area and
   call the gas utility or 911, or shut off the main if it is safe to reach -- never
   repair steps.

Keep it concise, respectful, and firm. Declining to explain the repair is the correct
behavior here; the genuinely helpful act is steering the user to safety.
```

---

### Grounding the refuse response

*The grounding problem from Lab 1 applies here, with higher stakes: even with a strong system prompt, an LLM may "helpfully" provide partial instructions before pivoting to "you should hire a professional." How will you prevent that?*

*Hint: "be careful" doesn't work. Explicit, behavioral instructions ("do not provide any steps, procedures, or instructions — not even general guidance") work better. What will yours say?*

```
The grounding is behavioral and enumerated, not attitudinal. Rather than telling the
model to "be safe," the refuse prompt lists the exact behaviors that count as leaking
instructions and bans each one, because that is where a well-meaning model fails:

  - "Partial-then-pivot" -- the most common leak: a few real steps, then "...but you
    should hire a pro." Banned explicitly ("do not begin to explain and then pivot").
  - "How a professional does it" -- a reframing that still hands over the procedure.
    Banned explicitly.
  - "Just explain it generally / I'm experienced / it's an emergency" -- social
    pressure that talks models past a soft rule. The prompt pre-commits the model to
    hold the line regardless of who is asking or how.
  - Tool/material/parts lists -- implicit how-to. Banned alongside steps.

We also give the model a constructive alternative so "refuse" does not read as a dead
end: name the hazard, name the right professional, and -- only for active dangers --
emergency-safety direction (leave, call the utility/911), which is safety guidance, not
repair guidance. Generation runs at a low temperature to keep the refusal tight and
reduce the chance of an improvised, chatty answer that wanders into specifics.
```

---

### Fallback for unknown tier

*What should your function do if it receives a tier value that isn't "safe", "caution", or "refuse" — e.g., "unknown" while the classifier is still a stub? Write the fallback behavior and explain why.*

```
Any tier that is not exactly "safe", "caution", or "refuse" is treated as "caution" --
the function selects the caution system prompt and answers with it.

Why caution: this mirrors the classifier's fail-closed default. An unrecognized tier
(e.g. "unknown" from the stub, or a typo) means we do not actually know the risk level.
Falling back to "safe" would answer a possibly-dangerous question with no warnings
(fail open -- the worst error); falling back to "refuse" would block harmless questions
and make the tool useless on any glitch. "caution" gives a useful answer that still
carries safety warnings and a professional recommendation -- the safe middle.

Separately, if the Groq API call itself raises, the function does not crash: it returns
a short plain-string message stating it could not generate a response and recommending
the user consult a licensed professional for anything involving electrical, gas,
plumbing, or structural work.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 3.*

**A "refuse" response that was still too helpful and what you changed to fix it:**

```
Early refuse drafts (before the enumerated ban list) tended to do the
"partial-then-pivot": for "Can I add a new electrical outlet to my garage?" the model
would name a couple of real actions ("you'd run a new circuit from the panel...") and
THEN say "but you should hire an electrician." That leading clause is exactly the leak.

Fix: I replaced the soft "don't give dangerous instructions" wording with an explicit,
enumerated ban -- no steps, no tool/material lists, no "how a pro does it," and a
specific line forbidding "begin to explain and then pivot," plus a clause that the rule
holds even if the user claims experience or urgency. After that, the refuse responses
named the hazard and the right professional without any procedural content.

Separately (not a too-helpful problem, but a safety-layer problem): the endpoint once
returned a degenerate token-repetition response ("uests uests uests..."). I added a
_looks_degenerate() guard in code that swaps any such response for a safe fallback
message, so the safety layer never ships garbage.
```

**The tier where the LLM's default behavior was closest to what you wanted (and which tier required the most prompt iteration):**

```
Closest to default: "safe". The model already wants to be a helpful step-by-step
assistant, so the safe prompt barely fights the grain -- it just needed to stay on
topic and hand off if the task turns out to be bigger than a fixture.

Most iteration: "refuse", by a wide margin. The model's default instinct is to be
helpful, which directly conflicts with withholding instructions, so a vague prompt
leaks every time. It only became reliable once the prohibition was behavioral and
enumerated rather than attitudinal. "caution" was in the middle -- the instructions
came for free, but getting the safety warnings to be firm (a real "stop and call a
pro") rather than a tacked-on disclaimer took a couple of passes.
```
