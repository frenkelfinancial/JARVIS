"""
Commission Tracking Agent
Supports: Google Sheets or Airtable as data source.
Set GOOGLE_SHEETS_CREDENTIALS_JSON + COMMISSION_SHEET_ID  — OR —
    AIRTABLE_API_KEY + AIRTABLE_BASE_ID + AIRTABLE_COMMISSION_TABLE
"""
import os
import json
import requests
from datetime import date, timedelta
import memory_store


class CommissionAgent:
    name = "commission"

    def run(self) -> str:
        try:
            if os.getenv("AIRTABLE_API_KEY"):
                return self._run_airtable()
            elif os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON"):
                return self._run_sheets()
            else:
                return self._run_demo()
        except Exception as e:
            msg = f"Commission Agent error: {e}"
            memory_store.update_agent(self.name, msg)
            return msg

    # ── Airtable ──────────────────────────────────────────────

    def _run_airtable(self) -> str:
        api_key = os.environ["AIRTABLE_API_KEY"]
        base_id = os.environ["AIRTABLE_BASE_ID"]
        table = os.environ.get("AIRTABLE_COMMISSION_TABLE", "Commissions")
        today = date.today()
        week_ago = today - timedelta(days=7)

        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "filterByFormula": f"AND(IS_AFTER({{Date}}, '{week_ago}'), IS_BEFORE({{Date}}, '{today + timedelta(days=1)}'))",
            "fields[]": ["Policy Number", "Carrier", "Commission Amount", "Status", "Date"],
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        records = resp.json().get("records", [])

        total = sum(float(r["fields"].get("Commission Amount", 0)) for r in records)
        pending = [r for r in records if r["fields"].get("Status") == "Pending"]
        paid = [r for r in records if r["fields"].get("Status") == "Paid"]

        summary = (
            f"COMMISSIONS (7-day)\n"
            f"  Policies tracked: {len(records)}\n"
            f"  Total: ${total:,.2f}\n"
            f"  Paid: {len(paid)} | Pending: {len(pending)}"
        )
        memory_store.update_agent(self.name, summary, {"total": total, "count": len(records)})
        return summary

    # ── Google Sheets ─────────────────────────────────────────

    def _run_sheets(self) -> str:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds_path = os.environ["GOOGLE_SHEETS_CREDENTIALS_JSON"]
        sheet_id = os.environ["COMMISSION_SHEET_ID"]
        creds = Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Sheet1!A2:E")
            .execute()
        )
        rows = result.get("values", [])

        total = 0.0
        for row in rows:
            try:
                total += float(str(row[3]).replace("$", "").replace(",", ""))
            except (IndexError, ValueError):
                pass

        summary = (
            f"COMMISSIONS (Sheets)\n"
            f"  Rows found: {len(rows)}\n"
            f"  Total: ${total:,.2f}"
        )
        memory_store.update_agent(self.name, summary, {"total": total, "rows": len(rows)})
        return summary

    # ── Demo / no credentials ─────────────────────────────────

    def _run_demo(self) -> str:
        prev = memory_store.get_agent(self.name)
        prev_total = prev.get("data", {}).get("total", 0)
        msg = (
            f"COMMISSIONS\n"
            f"  [Demo mode — connect Airtable or Google Sheets via .env]\n"
            f"  Last recorded total: ${prev_total:,.2f}"
        )
        memory_store.update_agent(self.name, msg)
        return msg
