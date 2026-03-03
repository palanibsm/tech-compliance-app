import os
from dotenv import load_dotenv

load_dotenv()


def get_azure_config() -> dict:
    """Read Azure OpenAI config from environment at call time (not import time)."""
    return {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        "api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
        "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        "api_version": os.getenv("AZURE_API_VERSION", "2024-02-15-preview"),
    }


# Matching confidence thresholds
FUZZY_AUTO_ACCEPT = 85   # >= 85: accept without AI review
FUZZY_SEND_TO_AI = 60    # 60–84: send to AI for validation; <60: no match

# Hostname prefixes to include
HOSTNAME_PREFIXES = ("P", "D")

# Software name patterns to exclude (case-insensitive)
EXCLUDE_PATTERNS = [
    r"^kb\d+",                  # KB patches e.g. KB123456
    r"hotfix",
    r"security update",
    r"cumulative update",
    r"update rollup",
    r"service pack",
    r"malicious software removal",
    r"windows defender update",
    r"definition update",
]
