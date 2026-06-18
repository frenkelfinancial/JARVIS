"""
Lead Monitor Agent
Supports: HubSpot CRM  OR  GoHighLevel (GHL)
HubSpot: set HUBSPOT_API_KEY
GHL:     set GHL_API_KEY + GHL_LOCATION_ID
"""
import os
import requests
from datetime import datetime, timedelta, timezone
import memory_store


class LeadMonitorAgent:
    name = "lead_monitor"

    def run(self) -> str:
        try:
            if os.getenv("HUBSPOT_API_KEY"):
                return self._run_hubspot()
            elif os.getenv("GHL_API_KEY"):
                return self._run_ghl()
            else:
                return self._no_creds()
        except Exception as e:
            msg = f"Lead Monitor Agent error: {e}"
            memory_store.update_agent(self.name, msg)
            return msg

    # ── HubSpot ───────────────────────────────────────────────

    def _run_hubspot(self) -> str:
        api_key = os.environ["HUBSPOT_API_KEY"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        since = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000)

        resp = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/search",
            headers=headers,
            json={
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": str(since),
                    }]
                }],
                "properties": ["firstname", "lastname", "email", "lifecyclestage", "hs_lead_status"],
                "limit": 100,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        results = data.get("results", [])

        new_leads = [r for r in results if r["properties"].get("lifecyclestage") == "lead"]
        qualified = [r for r in results if r["properties"].get("lifecyclestage") == "qualifiedlead"]

        summary = (
            f"LEADS (24h via HubSpot)\n"
            f"  New contacts: {total}\n"
            f"  Leads: {len(new_leads)} | Qualified: {len(qualified)}"
        )
        memory_store.update_agent(self.name, summary, {"new_24h": total})
        return summary

    # ── GoHighLevel ───────────────────────────────────────────

    def _run_ghl(self) -> str:
        api_key = os.environ["GHL_API_KEY"]
        location_id = os.environ["GHL_LOCATION_ID"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = requests.get(
            "https://rest.gohighlevel.com/v1/contacts/",
            headers=headers,
            params={"locationId": location_id, "startAfter": since, "limit": 100},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        contacts = data.get("contacts", [])
        total = data.get("total", len(contacts))

        new_count = len([c for c in contacts if c.get("type") == "lead"])

        summary = (
            f"LEADS (24h via GoHighLevel)\n"
            f"  New contacts: {total}\n"
            f"  Flagged as lead: {new_count}"
        )
        memory_store.update_agent(self.name, summary, {"new_24h": total})
        return summary

    # ── No credentials ────────────────────────────────────────

    def _no_creds(self) -> str:
        prev = memory_store.get_agent(self.name)
        prev_new = prev.get("data", {}).get("new_24h", 0)
        msg = (
            f"LEADS\n"
            f"  [Demo mode — set HUBSPOT_API_KEY or GHL_API_KEY in .env]\n"
            f"  Last recorded new leads: {prev_new}"
        )
        memory_store.update_agent(self.name, msg)
        return msg
