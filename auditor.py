import json
import os
from datetime import datetime, timezone
from config import (
    LOG_FILE,
    LLM_MODEL,
    SESSION_SUMMARY_FILE,
    SUMMARY_INTERVAL,
    VALID_TIERS,
)

# Truncation limits (see specs/auditor-spec.md): log enough to diagnose, not
# enough to become a storage/PII liability.
_QUESTION_LIMIT = 300
_RESPONSE_PREVIEW_LIMIT = 200
_CONSOLE_QUESTION_LIMIT = 60


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

    # Rolling aggregate metrics — also a side effect that must never raise.
    _maybe_write_session_summary()


def _read_audit_records() -> list:
    """
    Read and parse every record in the audit log, oldest first.

    Tolerant of a missing file (returns []) and of individual malformed lines
    (skipped), so a single corrupt entry can never break summary generation.
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
    Every SUMMARY_INTERVAL interactions, append a rolling summary to
    SESSION_SUMMARY_FILE.

    The summary is computed by reading and parsing the audit log (rather than
    holding an in-memory counter), so it stays correct across restarts and only
    fires when the cumulative interaction count is an exact multiple of the
    interval. Like all logging here, failures are reported but never raised.
    """
    try:
        records = _read_audit_records()
        total = len(records)
        if total == 0 or total % SUMMARY_INTERVAL != 0:
            return

        distribution = {t: 0 for t in sorted(VALID_TIERS)}
        for rec in records:
            tier = rec.get("tier")
            if tier in distribution:
                distribution[tier] += 1

        recent_questions = [
            rec.get("question", "") for rec in records[-3:]
        ][::-1]  # most recent first

        summary_record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_interactions": total,
            "tier_distribution": distribution,
            "recent_questions": recent_questions,
        }

        summary_dir = os.path.dirname(SESSION_SUMMARY_FILE)
        if summary_dir:
            os.makedirs(summary_dir, exist_ok=True)
        with open(SESSION_SUMMARY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary_record, ensure_ascii=False) + "\n")

        print(f"[SUMMARY] {total} interactions logged -> {SESSION_SUMMARY_FILE}")
    except Exception as exc:  # never let summary generation break the request
        print(f"[log_interaction] failed to write session summary: {exc}")
