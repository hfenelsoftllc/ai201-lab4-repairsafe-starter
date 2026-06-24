from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Prompt (see specs/classifier-spec.md). The system message is static; only the
# user message carries the question, so the two roles stay cleanly separated.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a safety classifier for a home-repair assistant. Your only job is to label a \
home-repair question into exactly one safety tier. You do NOT answer the repair \
question and you do NOT give instructions.

Classify the REPAIR ITSELF, based on what the work physically requires and its worst \
realistic failure mode -- never on who you imagine is asking. The decisive test: \
"If this repair goes wrong, can it cause fire, flooding, structural failure, injury, \
or death?"

Tiers:
- safe: Routine, low-risk repairs a typical homeowner can do with basic tools. Worst \
case of a mistake is cosmetic damage or a broken fixture. No permit, no license. \
Examples: patching small drywall holes, painting, replacing a light bulb, plunging a \
drain, tightening hardware, swapping a toilet seat, cleaning/replacing an HVAC filter.
- caution: Doable for a motivated homeowner without a permit, but touches water or \
electricity where a mistake has real cost or mild injury risk -- yet stays recoverable \
(a leak, a tripped breaker, a ruined fixture). Examples: replacing a faucet, replacing \
a toilet or flapper, like-for-like swap of a GFCI outlet or light switch at the SAME \
location, replacing an existing light fixture/ceiling fan at the same location, \
installing a smart thermostat in place of an existing one, re-grouting tile, replacing \
a showerhead, patching large drywall holes.
- refuse: An amateur mistake can cause fire, flooding, structural failure, serious \
injury, or death, OR local code requires a licensed professional and a permit. Give no \
DIY instructions. Examples: any electrical panel/service work, ADDING new outlets, \
circuits, or switches (new wiring), any gas line or gas appliance work, removing or \
modifying a wall not confirmed non-load-bearing, replacing the main water shutoff, \
replacing a water heater, running new plumbing lines, foundation work, structural roof \
repairs.

Boundary rules (these decide most hard cases):
- "Replacing/swapping" an existing component at the same location is caution. \
"Adding/installing new" anything that requires running new wire or pipe is refuse.
- Anything involving gas is always refuse. There is no safe DIY gas repair.
- Removing any wall is refuse unless the user states a structural engineer already \
confirmed it is non-load-bearing.
- Water heater replacement is refuse unless the question is clearly limited to a minor \
component (anode rod, heating element).
- Judge by what the repair actually requires, not how small the user makes it sound \
("I just want to move the switch six inches" is still refuse).
- If the question is genuinely ambiguous or under-specified, choose the SAFER (higher) \
tier.

Output format -- reply with exactly these two lines and nothing else:
Reason: <one sentence>
Tier: <safe | caution | refuse>"""

USER_TEMPLATE = 'Classify this home-repair question:\n\n"{question}"'

# Returned when the model call fails or its reply can't be parsed/validated.
# We fail CLOSED to "caution": never let an unclassifiable question through as
# "safe", but don't escalate a parsing accident all the way to "refuse" either.
_FALLBACK = {
    "tier": "caution",
    "reason": "Could not classify reliably; defaulting to caution for safety.",
}


def _parse(text: str):
    """
    Pull (tier, reason) out of the model's two-line reply.

    Tolerant of casing, surrounding markdown/punctuation, and trailing prose:
    we scan line by line for the "tier:" and "reason:" prefixes and keep the
    first VALID_TIERS token we find after "tier:". Returns None if no valid
    tier line is present.
    """
    tier = None
    reason = ""
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if tier is None and lowered.startswith("tier:"):
            after = stripped.split(":", 1)[1].lower()
            for token in after.replace("*", " ").replace("`", " ").split():
                cleaned = token.strip(".,!()[]<>\"'*` ")
                if cleaned in VALID_TIERS:
                    tier = cleaned
                    break
        elif lowered.startswith("reason:"):
            reason = stripped.split(":", 1)[1].strip(" *`")

    if tier is None:
        return None
    if not reason:
        reason = f"Classified as {tier}."
    return tier, reason


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    Implements specs/classifier-spec.md (Milestone 1): an LLM-as-judge call that
    labels the question as "safe", "caution", or "refuse" and explains why.

    Steps:
      1. Build a static system prompt (tier definitions + boundary rules) and a
         user message carrying the question.
      2. Send a single chat completion request (no tools, no history).
      3. Parse the tier and reason out of the raw response text.
      4. Validate the tier against VALID_TIERS; fall back to "caution" if the
         response can't be parsed, the tier isn't recognized, or the API errors.

    Returns a dict with:
      - "tier"   : str -- one of "safe", "caution", "refuse"
      - "reason" : str -- a brief explanation of why this tier was assigned
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(question=question)},
            ],
        )
        raw = completion.choices[0].message.content or ""
    except Exception as exc:  # network/auth/rate-limit -- fail closed, don't crash
        print(f"[classify_safety_tier] API call failed: {exc}")
        return dict(_FALLBACK)

    parsed = _parse(raw)
    if parsed is None:
        return dict(_FALLBACK)

    tier, reason = parsed
    if tier not in VALID_TIERS:  # belt-and-suspenders; _parse already filters
        return dict(_FALLBACK)

    return {"tier": tier, "reason": reason}
