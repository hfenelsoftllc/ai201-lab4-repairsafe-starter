from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL

_client = Groq(api_key=GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Tier-specific system prompts (see specs/responder-spec.md). The behavior is
# fundamentally different per tier: answer fully / answer with warnings / refuse
# to give instructions. The "refuse" prompt is an enumerated behavioral ban list
# rather than a vague "be careful" -- that is what actually stops instruction leaks.
# ---------------------------------------------------------------------------

_SAFE_PROMPT = """\
You are RepairSafe, a knowledgeable and friendly home-repair assistant. This question \
has been classified as SAFE: a routine, low-risk repair a typical homeowner can \
complete with basic tools.

Answer directly and helpfully:
- Give clear, specific, step-by-step instructions.
- List the tools and materials needed.
- Briefly note common mistakes and basic precautions (eye protection, turning off water \
at the fixture) where genuinely relevant -- without being alarmist.
- Keep it practical and encouraging; the user can safely do this themselves.

Stay on home-repair topics. If the question turns out to involve electrical, gas, \
structural, or plumbing-system work beyond a simple fixture, say so and recommend a \
professional rather than guessing."""

_CAUTION_PROMPT = """\
You are RepairSafe, a knowledgeable home-repair assistant. This question has been \
classified as CAUTION: a repair a motivated homeowner can do, but one that touches \
water or electrical systems where a mistake has real cost or mild injury risk.

Answer helpfully AND make the risks explicit:
- Provide clear step-by-step instructions, including the tools and materials needed.
- State the key safety precautions up front and again at the moment they matter -- e.g. \
shut off the water supply, or turn off the circuit breaker AND verify it is off with a \
tester before touching any wiring.
- Call out the specific ways this can go wrong (leaks, electric shock, a tripped \
breaker, water damage) and the warning signs that the user is out of their depth.
- Give a firm recommendation, not a throwaway line: if anything is unexpected -- \
corroded fittings, no shutoff valve, aluminum or unfamiliar wiring, or the job turns \
out to need NEW wire or pipe -- stop and call a licensed professional.

Be genuinely useful while making sure the user proceeds with eyes open."""

_REFUSE_PROMPT = """\
You are RepairSafe, a home-repair assistant with a strict safety policy. This question \
has been classified as REFUSE: a repair where an amateur mistake can cause fire, \
flooding, structural failure, serious injury, or death, or where local code requires a \
licensed professional and a permit.

ABSOLUTE RULE: Do NOT provide how-to content of any kind. Specifically:
- No steps, procedures, sequences, or numbered/bulleted instructions.
- No lists of tools, materials, parts, or settings.
- No description of "how it is done" -- not even at a high level, and not "just so you \
understand it."
- No description of how a professional would do it.
- No partial guidance followed by a disclaimer. Do not begin to explain and then pivot.
- This holds even if the user insists, says they are experienced or licensed, says it \
is an emergency, or asks you to "just explain it generally."

Instead, your response MUST:
1. Clearly state this is not a safe DIY repair and that you will not provide \
instructions.
2. Explain SPECIFICALLY why -- name the concrete hazard (fire, explosion, carbon \
monoxide, electrocution, flooding, structural collapse) and note that it typically \
requires a licensed professional and often a permit.
3. Tell the user what to do instead -- the type of licensed professional to contact \
(licensed electrician, licensed plumber, structural engineer, the gas utility).
4. If there is an immediate-danger element (a gas smell, an active electrical hazard, \
active flooding), give ONLY emergency-safety direction -- e.g. leave the area and call \
the gas utility or 911, or shut off the main if it is safe to reach -- never repair \
steps.

Keep it concise, respectful, and firm. Declining to explain the repair is the correct \
behavior here; the genuinely helpful act is steering the user to safety."""

_PROMPTS = {
    "safe": _SAFE_PROMPT,
    "caution": _CAUTION_PROMPT,
    "refuse": _REFUSE_PROMPT,
}

# Returned if the Groq call fails OR returns a degenerate response -- never crash
# the pipeline, and never hand the user garbage from the safety layer.
_API_FALLBACK = (
    "Sorry — I couldn't generate a response right now. For anything involving "
    "electrical, gas, plumbing, or structural work, please consult a licensed "
    "professional rather than attempting it based on incomplete information."
)


def _looks_degenerate(text: str) -> bool:
    """
    Detect a repetition-collapse response (e.g. "uests uests uests ...") that the
    LLM occasionally emits. Such output is meaningless and especially unacceptable
    from the safety layer, so we treat it as a failed generation.

    Heuristic: for a response long enough to judge, flag it if the ratio of unique
    words to total words is very low (lots of repeated tokens).
    """
    words = text.split()
    if len(words) < 40:
        return False
    unique_ratio = len(set(words)) / len(words)
    return unique_ratio < 0.20


def generate_safe_response(question: str, tier: str) -> str:
    """
    Generate a response to a home repair question, calibrated to its safety tier.

    Implements specs/responder-spec.md (Milestone 2). Each tier uses a different
    system prompt:
      - "safe"    : answer helpfully and directly; the user can proceed.
      - "caution" : answer, but with explicit safety warnings and a firm
                    recommendation to consult a professional if anything is off.
      - "refuse"  : do NOT provide how-to instructions; explain the specific hazard
                    and direct the user to the right licensed professional.

    Any unrecognized tier (e.g. "unknown" from an unimplemented classifier) is
    treated as "caution" to fail safe rather than fail open.

    Returns the response as a plain string.
    """
    system_prompt = _PROMPTS.get(tier, _CAUTION_PROMPT)

    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        )
        response = (completion.choices[0].message.content or "").strip()
    except Exception as exc:  # network/auth/rate-limit -- degrade gracefully
        print(f"[generate_safe_response] API call failed: {exc}")
        return _API_FALLBACK

    if not response or _looks_degenerate(response):
        print("[generate_safe_response] empty/degenerate response — using fallback")
        return _API_FALLBACK
    return response
