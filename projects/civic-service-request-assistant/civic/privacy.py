"""Best-effort query redaction, plus allowlisted exports that omit ALL resident text."""

import re

PATTERNS = [
    r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
    r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)",
    r"\b[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d\b",
    r"\b\d+\s+[\w .'-]+\s(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln)\b",
    r"\b(?:my name is|i am|i'm)\s+[\w'-]+(?:\s+[\w'-]+)?",
]


def redact(text: str) -> str:
    for pattern in PATTERNS:
        text = re.sub(pattern, "[redacted]", text, flags=re.I)
    return text


def export_fields(row: dict) -> dict:
    # Never attempt to scrub arbitrary notes or addresses into being safe to export.
    return {
        "Title": f"Service request {row['id'][:8]}",
        "RequestId": row["id"],
        "ServiceType": row["service"],
        "Department": row["department"],
        "Status": row["status"],
        "CreatedAt": row["created_at"],
        "UpdatedAt": row["updated_at"],
        "Version": row["version"],
    }
