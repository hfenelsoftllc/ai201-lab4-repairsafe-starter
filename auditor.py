import json
import os
from datetime import datetime, timezone
from config import LOG_FILE, SESSION_SUMMARY_FILE, SUMMARY_EVERY, LLM_MODEL, VALID_TIERS

# Truncation limits (see specs/auditor-spec.md): log enough to diagnose, not
# enough to become a storage/PII liability.
_QUESTION_LIMIT = 300
_RESPONSE_PREVIEW_LIMIT = 200
_CONSOLE_QUESTION_LIMIT = 60
_SUMMARY_RECENT_COUNT = 3


def log_interaction(question: str, tier: str, response: str) -> None:
    """
    Append a structured record of this interaction to the audit log.

    Implements specs/auditor-spec.md (Milestone 3). Writes one JSON object per line
    to LOG_FILE ("logs/audit.jsonl") and prints a one-line summary to the terminal.

    Logged fields:
      - "timestamp"        : ISO 8601 UTC datetime string
      - "tier"             : the safety tier assigned to this question
      - "question"         : the user's question (truncated to 300 chars)
      - "response_preview" : first 200 characters of the response
      - "model"            : the LLM that produced the response
      - "response_length"  : full character length of the response (pre-truncation)

    Logging is a side effect and must never break the pipeline: the logs/ directory
    is created if missing, and any write failure is reported but not raised.
    """
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    response_length = len(response)

    record = {
        "timestamp": timestamp,
        "tier": tier,
        "question": question[:_QUESTION_LIMIT],
        "response_preview": response[:_RESPONSE_PREVIEW_LIMIT],
        "model": LLM_MODEL,
        "response_length": response_length,
    }

    try:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # never let logging break the user-facing request
        print(f"[log_interaction] failed to write audit log: {exc}")
        return

    # Aggregated metrics: after every SUMMARY_EVERY interactions, roll up the
    # full audit log into one summary line. Best-effort, like the write above.
    _maybe_write_session_summary()

    short_q = question.replace("\n", " ").strip()
    if len(short_q) > _CONSOLE_QUESTION_LIMIT:
        short_q = short_q[:_CONSOLE_QUESTION_LIMIT] + "..."
    summary = f'[LOGGED] tier={tier} | "{short_q}" -> {response_length} chars'
    try:
        print(summary)
    except UnicodeEncodeError:
        # Some Windows consoles use a legacy codec (cp1252) that can't encode
        # arbitrary Unicode in the question; never let the console crash the request.
        print(summary.encode("ascii", "replace").decode("ascii"))


def _read_audit_records() -> list:
    """
    Parse the audit log into a list of interaction records (oldest first).

    The audit log is the single source of truth for per-interaction data, so we
    derive the session summary by reading it rather than holding state in memory
    (which would not survive a process restart anyway). Malformed lines are
    skipped so one bad row can't sink the whole rollup.
    """
    records = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return records


def _maybe_write_session_summary() -> None:
    """
    After every SUMMARY_EVERY interactions, append an aggregated summary line to
    SESSION_SUMMARY_FILE.

    The summary object reports:
      - "timestamp"          : when the summary was written (ISO 8601 UTC)
      - "total_interactions" : count of all logged interactions to date
      - "tier_distribution"  : how many of each tier (safe/caution/refuse, ...)
      - "recent_questions"   : the 3 most recent questions (most recent first)

    This is a side effect and, like the audit write, must never break the
    pipeline: any failure is reported to the console but not raised.
    """
    try:
        records = _read_audit_records()
        total = len(records)
        if total == 0 or total % SUMMARY_EVERY != 0:
            return

        # Seed every known tier at 0 so the distribution is stable across
        # summaries even before a given tier has been seen; count whatever
        # tiers actually appear in the log on top of that.
        distribution = {tier: 0 for tier in VALID_TIERS}
        for rec in records:
            tier = rec.get("tier", "unknown")
            distribution[tier] = distribution.get(tier, 0) + 1

        recent = [rec.get("question", "") for rec in records[-_SUMMARY_RECENT_COUNT:]]
        recent.reverse()  # most recent first

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_interactions": total,
            "tier_distribution": dict(sorted(distribution.items())),
            "recent_questions": recent,
        }

        summary_dir = os.path.dirname(SESSION_SUMMARY_FILE)
        if summary_dir:
            os.makedirs(summary_dir, exist_ok=True)

        with open(SESSION_SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

        print(
            f"[SUMMARY] {total} interactions | "
            f"{summary['tier_distribution']}"
        )
    except Exception as exc:  # never let the rollup break the user-facing request
        print(f"[_maybe_write_session_summary] failed to write session summary: {exc}")
