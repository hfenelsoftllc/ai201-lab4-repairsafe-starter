import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"
LOG_FILE = "logs/audit.jsonl"
SESSION_SUMMARY_FILE = "logs/session_summary.jsonl"
# Write an aggregated session summary after every Nth interaction.
SUMMARY_EVERY = 5
VALID_TIERS = {"safe", "caution", "refuse"}
