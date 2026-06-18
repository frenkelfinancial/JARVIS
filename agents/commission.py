"""
Commission Agent — reads carrier commission emails via Gmail API,
uses Claude to extract structured data, saves to memory/commission_memory.json.

Setup:
  1. Create OAuth credentials at console.cloud.google.com → APIs & Services
     → Credentials → OAuth 2.0 Client IDs (Desktop app)
  2. Download as credentials.json and place it in the Jarvis root folder
  3. First run opens a browser to authorize Gmail read access
  4. token.pickle is written automatically for all future runs
"""
import os
import json
import pickle
import base64
import re
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

import anthropic
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import memory_store

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

JARVIS_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = JARVIS_ROOT / "credentials.json"
TOKEN_PATH = JARVIS_ROOT / "token.pickle"
MEMORY_PATH = JARVIS_ROOT / "memory" / "commission_memory.json"

CARRIERS = [
    "corebridge",
    "americo",
    "transamerica",
    "american-amicable",
    "american amicable",
    "family first life",
]

KEYWORDS = [
    "commission statement",
    "policy issued",
    "chargeback",
]


# ── Gmail auth ────────────────────────────────────────────────────────────────

def _get_gmail_service():
    creds = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


# ── Gmail search ──────────────────────────────────────────────────────────────

def _build_query() -> str:
    carrier_terms = " OR ".join(
        f'"{c}"' for c in CARRIERS
    )
    keyword_terms = " OR ".join(
        f'"{k}"' for k in KEYWORDS
    )
    return f"({carrier_terms}) ({keyword_terms})"


def _extract_text(payload: dict) -> str:
    """Recursively pull plain-text body from a Gmail message payload."""
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        # recurse into multipart
        if part.get("parts"):
            result = _extract_text(part)
            if result:
                return result
    return ""


def _fetch_email(service, msg_id: str) -> tuple[str, str]:
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    subject = ""
    for header in msg.get("payload", {}).get("headers", []):
        if header["name"].lower() == "subject":
            subject = header["value"]
            break

    snippet = msg.get("snippet", "")
    body = _extract_text(msg.get("payload", {}))
    # cap body length sent to Claude
    content = (snippet + "\n" + body)[:3000]
    return subject, content


# ── Claude extraction ─────────────────────────────────────────────────────────

def _parse_with_claude(subject: str, body: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = (
        "You are parsing a life insurance commission email. "
        "Return ONLY a JSON object — no explanation.\n\n"
        f"Subject: {subject}\n"
        f"Email excerpt:\n{body}\n\n"
        "JSON fields:\n"
        '  "carrier": carrier name string or null\n'
        '  "amount": dollar amount as a number or null\n'
        '  "policy_number": policy number string or null\n'
        '  "type": "commission" or "chargeback"\n'
        '  "description": one-line plain-English summary\n'
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # strip markdown fences if present
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "carrier": None,
            "amount": None,
            "policy_number": None,
            "type": "commission",
            "description": subject[:120],
        }


# ── Memory helpers ────────────────────────────────────────────────────────────

def _load_commission_memory() -> dict:
    if MEMORY_PATH.exists():
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    return {"records": [], "last_updated": None}


def _save_commission_memory(data: dict):
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Agent ─────────────────────────────────────────────────────────────────────

class CommissionAgent:
    name = "commission"

    def run(self) -> str:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "COMMISSION\n  Skipped — ANTHROPIC_API_KEY not set in .env"

        if not CREDENTIALS_PATH.exists():
            return (
                "COMMISSION\n"
                "  Skipped — credentials.json not found.\n"
                "  Create OAuth credentials at console.cloud.google.com\n"
                "  and save as credentials.json in the Jarvis folder."
            )

        try:
            service = _get_gmail_service()
        except Exception as e:
            return f"COMMISSION\n  Gmail auth failed: {e}"

        query = _build_query()
        try:
            results = service.users().messages().list(
                userId="me", q=query, maxResults=25
            ).execute()
        except Exception as e:
            return f"COMMISSION\n  Gmail search error: {e}"

        messages = results.get("messages", [])

        memory = _load_commission_memory()
        seen_ids = {r.get("gmail_id") for r in memory.get("records", [])}

        new_records = []
        for msg in messages:
            if msg["id"] in seen_ids:
                continue
            try:
                subject, body = _fetch_email(service, msg["id"])
                parsed = _parse_with_claude(subject, body)
                parsed["gmail_id"] = msg["id"]
                parsed["fetched_at"] = datetime.now().isoformat()
                new_records.append(parsed)
            except Exception:
                continue

        if new_records:
            memory.setdefault("records", []).extend(new_records)
            _save_commission_memory(memory)

        # ── build summary ──────────────────────────────────────
        all_records = memory.get("records", [])
        commissions = [
            r for r in all_records
            if r.get("type") == "commission" and isinstance(r.get("amount"), (int, float))
        ]
        chargebacks = [
            r for r in all_records
            if r.get("type") == "chargeback" and isinstance(r.get("amount"), (int, float))
        ]

        total_in = sum(r["amount"] for r in commissions)
        total_cb = sum(r["amount"] for r in chargebacks)
        net = total_in - total_cb

        lines = []
        if commissions:
            lines.append(
                f"{len(commissions)} commission{'s' if len(commissions) != 1 else ''} "
                f"totaling ${total_in:,.2f}"
            )
        if chargebacks:
            cb = chargebacks[-1]
            carrier = cb.get("carrier") or "unknown carrier"
            amt = cb.get("amount", 0)
            lines.append(
                f"{len(chargebacks)} chargeback{'s' if len(chargebacks) != 1 else ''} "
                f"from {carrier} for ${amt:,.2f}"
            )
        if lines:
            lines.append(f"Net: ${net:,.2f}")

        body_text = ". ".join(lines) if lines else "No commission records yet."
        new_label = f"({len(new_records)} new)" if new_records else "(no new emails)"
        summary = f"COMMISSION  {new_label}\n  {body_text}"

        memory_store.update_agent(
            self.name,
            summary,
            {"total_commissions": total_in, "total_chargebacks": total_cb, "net": net},
        )
        return summary
