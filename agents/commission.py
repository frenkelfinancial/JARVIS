"""
Email Intelligence Agent — scans ALL inbox emails via Gmail API.
Uses Claude to classify each email into:
  - commission : carrier commission statements & chargebacks
  - policy     : policy status updates (pending, issued, approved, declined)
  - expense    : business expenses & monthly subscriptions
  - irrelevant : everything else (skipped)

Saves structured records to memory/email_intel_memory.json.
"""
import os
import sys
import json
import base64
import re
from pathlib import Path
from datetime import datetime, date

from dotenv import load_dotenv
load_dotenv()

import anthropic
import memory_store

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gmail_auth import get_gmail_service

JARVIS_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = JARVIS_ROOT / "credentials.json"
MEMORY_PATH = JARVIS_ROOT / "memory" / "email_intel_memory.json"

MAX_EMAILS_PER_RUN = 100
BATCH_SIZE = 30
MAX_SEEN_IDS = 2000


# ── Gmail helpers ─────────────────────────────────────────────────────────────

def _get_metadata(service, msg_id: str) -> dict:
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["Subject", "From"]
    ).execute()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "subject": headers.get("subject", "(no subject)"),
        "sender": headers.get("from", ""),
        "snippet": msg.get("snippet", ""),
    }


def _extract_text(payload: dict) -> str:
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        if part.get("parts"):
            result = _extract_text(part)
            if result:
                return result
    return ""


def _get_full_body(service, msg_id: str) -> tuple[str, str, str]:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    subject = headers.get("subject", "(no subject)")
    sender = headers.get("from", "")
    snippet = msg.get("snippet", "")
    body = _extract_text(msg.get("payload", {}))
    return subject, sender, (snippet + "\n" + body)[:3000]


# ── Claude helpers ────────────────────────────────────────────────────────────

def _claude(prompt: str, max_tokens: int = 512) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _parse_json(text: str, default):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def _classify_batch(metas: list[dict]) -> list[str]:
    lines = [
        f'{i}: From: {m["sender"]} | Subject: {m["subject"]} | Preview: {m["snippet"][:100]}'
        for i, m in enumerate(metas)
    ]
    prompt = (
        "You are classifying emails for Jace Frenkel, an independent life insurance agent.\n\n"
        "Classify each email into ONE category:\n"
        '- "commission" — carrier commission statements, payment deposits, chargeback notices\n'
        '- "policy" — policy status updates, approvals, pending applications, underwriting decisions, welcome letters\n'
        '- "expense" — business expenses, software subscriptions, monthly charges, receipts, invoices\n'
        '- "irrelevant" — newsletters, spam, personal email, marketing, anything not business-critical\n\n'
        "Return ONLY a JSON array of strings, one per email, in the same order.\n"
        'Example: ["irrelevant", "commission", "policy", "expense"]\n\n'
        "Emails:\n" + "\n".join(lines)
    )
    result = _parse_json(_claude(prompt), default=["irrelevant"] * len(metas))
    if not isinstance(result, list) or len(result) != len(metas):
        return ["irrelevant"] * len(metas)
    return result


def _extract_commission(subject: str, sender: str, body: str) -> dict:
    text = _claude(
        "Parse this insurance commission email. Return ONLY JSON.\n\n"
        f"Subject: {subject}\nFrom: {sender}\n\n{body}\n\n"
        'JSON fields:\n'
        '  "carrier": carrier name string or null\n'
        '  "amount": dollar amount as number or null\n'
        '  "policy_number": string or null\n'
        '  "type": "commission" or "chargeback"\n'
        '  "description": one-line summary\n'
    )
    return _parse_json(text, {
        "carrier": None, "amount": None, "policy_number": None,
        "type": "commission", "description": subject[:120],
    })


def _extract_policy(subject: str, sender: str, body: str) -> dict:
    text = _claude(
        "Parse this insurance policy status email. Return ONLY JSON.\n\n"
        f"Subject: {subject}\nFrom: {sender}\n\n{body}\n\n"
        'JSON fields:\n'
        '  "carrier": carrier name string or null\n'
        '  "policy_number": string or null\n'
        '  "client_name": insured client name or null\n'
        '  "status": short status (e.g. "Issued", "Pending", "Approved", "Declined", "In Underwriting", "Lapsed")\n'
        '  "description": one-line summary\n'
    )
    return _parse_json(text, {
        "carrier": None, "policy_number": None, "client_name": None,
        "status": "Unknown", "description": subject[:120],
    })


def _extract_expense(subject: str, sender: str, body: str) -> dict:
    text = _claude(
        "Parse this business expense or subscription email. Return ONLY JSON.\n\n"
        f"Subject: {subject}\nFrom: {sender}\n\n{body}\n\n"
        'JSON fields:\n'
        '  "vendor": company or service name\n'
        '  "amount": dollar amount as number or null\n'
        '  "billing_period": "monthly", "annual", or "one-time"\n'
        '  "description": one-line summary\n'
    )
    return _parse_json(text, {
        "vendor": sender.split("<")[0].strip() or sender,
        "amount": None, "billing_period": "monthly",
        "description": subject[:120],
    })


# ── Memory helpers ────────────────────────────────────────────────────────────

def _load_memory() -> dict:
    if MEMORY_PATH.exists():
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    return {"seen_ids": [], "commissions": [], "policies": [], "expenses": [], "last_updated": None}


def _save_memory(data: dict):
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # keep seen_ids from growing unbounded
    if len(data.get("seen_ids", [])) > MAX_SEEN_IDS:
        data["seen_ids"] = data["seen_ids"][-MAX_SEEN_IDS:]
    data["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Agent ─────────────────────────────────────────────────────────────────────

class CommissionAgent:
    name = "commission"

    def run(self) -> str:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "EMAIL INTEL\n  Skipped — ANTHROPIC_API_KEY not set"
        if not CREDENTIALS_PATH.exists():
            return "EMAIL INTEL\n  Skipped — credentials.json not found"

        try:
            service = get_gmail_service()
        except Exception as e:
            return f"EMAIL INTEL\n  Gmail auth failed: {e}"

        try:
            result = service.users().messages().list(
                userId="me", maxResults=MAX_EMAILS_PER_RUN
            ).execute()
        except Exception as e:
            return f"EMAIL INTEL\n  Gmail fetch error: {e}"

        messages = result.get("messages", [])
        memory = _load_memory()
        seen_ids = set(memory.get("seen_ids", []))
        new_messages = [m for m in messages if m["id"] not in seen_ids]

        if not new_messages:
            return self._build_summary(memory, new_count=0)

        # get metadata (subject + sender) without fetching bodies
        metas = []
        for m in new_messages:
            try:
                metas.append(_get_metadata(service, m["id"]))
            except Exception:
                metas.append({"id": m["id"], "subject": "", "sender": "", "snippet": ""})

        # batch classify
        categories = []
        for i in range(0, len(metas), BATCH_SIZE):
            batch = metas[i:i + BATCH_SIZE]
            try:
                cats = _classify_batch(batch)
            except Exception:
                cats = ["irrelevant"] * len(batch)
            categories.extend(cats)

        # extract details only for relevant emails
        new_count = 0
        today_str = date.today().isoformat()
        for meta, category in zip(metas, categories):
            seen_ids.add(meta["id"])
            if category == "irrelevant":
                continue
            try:
                subject, sender, body = _get_full_body(service, meta["id"])
                record = {"gmail_id": meta["id"], "date": today_str, "fetched_at": datetime.now().isoformat()}

                if category == "commission":
                    data = _extract_commission(subject, sender, body)
                    data.update(record)
                    memory.setdefault("commissions", []).append(data)

                elif category == "policy":
                    data = _extract_policy(subject, sender, body)
                    data.update(record)
                    memory.setdefault("policies", []).append(data)

                elif category == "expense":
                    data = _extract_expense(subject, sender, body)
                    data.update(record)
                    memory.setdefault("expenses", []).append(data)

                new_count += 1
            except Exception:
                continue

        memory["seen_ids"] = list(seen_ids)
        _save_memory(memory)
        return self._build_summary(memory, new_count=new_count)

    def _build_summary(self, memory: dict, new_count: int) -> str:
        lines = [f"EMAIL INTEL  ({new_count} new)"]

        # ── Commissions ───────────────────────────────────────────────────────
        all_comm = memory.get("commissions", [])
        commissions = [r for r in all_comm if r.get("type") != "chargeback"]
        chargebacks = [r for r in all_comm if r.get("type") == "chargeback"]
        total_in = sum(r.get("amount") or 0 for r in commissions)
        total_cb = sum(r.get("amount") or 0 for r in chargebacks)
        net = total_in - total_cb

        lines.append("\n  COMMISSIONS")
        if commissions or chargebacks:
            lines.append(f"    {len(commissions)} received: ${total_in:,.2f}")
            if chargebacks:
                lines.append(f"    {len(chargebacks)} chargeback(s): ${total_cb:,.2f}")
            lines.append(f"    Net: ${net:,.2f}")
        else:
            lines.append("    No records yet")

        # ── Policy Status ─────────────────────────────────────────────────────
        policies = memory.get("policies", [])
        lines.append("\n  POLICY STATUS")
        if policies:
            active_statuses = {"pending", "in underwriting", "approved", "submitted"}
            active = [p for p in policies if (p.get("status") or "").lower() in active_statuses]
            recent_issued = [p for p in policies if (p.get("status") or "").lower() in ("issued", "declined", "lapsed")][-5:]

            if active:
                lines.append("    Active / Pending:")
                for p in active[-8:]:
                    client = p.get("client_name") or "Unknown"
                    carrier = p.get("carrier") or ""
                    pol = p.get("policy_number") or ""
                    status = p.get("status") or "?"
                    detail = " | ".join(filter(None, [carrier, client, pol]))
                    lines.append(f"    [~] {status}: {detail}")

            if recent_issued:
                lines.append("    Recent decisions:")
                for p in recent_issued:
                    icon = "[+]" if (p.get("status") or "").lower() == "issued" else "[-]"
                    client = p.get("client_name") or "Unknown"
                    carrier = p.get("carrier") or ""
                    status = p.get("status") or "?"
                    detail = " | ".join(filter(None, [carrier, client]))
                    lines.append(f"    {icon} {status}: {detail}")

            if not active and not recent_issued:
                for p in policies[-5:]:
                    lines.append(f"    • {p.get('status', '?')}: {p.get('description', '')[:80]}")
        else:
            lines.append("    No policy updates yet")

        # ── Expenses ──────────────────────────────────────────────────────────
        expenses = memory.get("expenses", [])
        lines.append("\n  EXPENSES / SUBSCRIPTIONS")
        if expenses:
            this_month = date.today().strftime("%Y-%m")
            mtd = [e for e in expenses if e.get("date", "").startswith(this_month)]
            mtd_total = sum(e.get("amount") or 0 for e in mtd)
            all_time_total = sum(e.get("amount") or 0 for e in expenses)

            lines.append(f"    MTD: ${mtd_total:,.2f}  |  All-time: ${all_time_total:,.2f}")
            for e in expenses[-8:]:
                vendor = e.get("vendor", "Unknown")
                amt = e.get("amount")
                period = e.get("billing_period", "")
                amt_str = f"${amt:,.2f}" if amt else "?"
                period_str = period if period and period != "None" else "recurring"
                lines.append(f"    {amt_str} - {vendor} ({period_str})")
        else:
            lines.append("    No expenses tracked yet")

        summary = "\n".join(lines)
        memory_store.update_agent(
            self.name, summary,
            {
                "net_commission": net,
                "active_policies": len([p for p in policies if (p.get("status") or "").lower() in ("pending", "in underwriting", "approved", "submitted")]),
                "expense_count": len(expenses),
            },
        )
        return summary
