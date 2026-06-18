"""
main.py — Jarvis Agent Orchestrator
Runs all agents on schedule and sends daily briefs via Telnyx SMS.

Usage:
  python main.py          — starts the scheduler (keeps running)
  python main.py --now    — fires run_all_agents() immediately, then exits
"""
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

from jarvis import build_daily_brief
from sms import start_sms_server
from agents import (
    CommissionAgent,
    LeadMonitorAgent,
    EcommerceAgent,
    VideoPipelineAgent,
    IncomeGoalsAgent,
    VideoScriptAgent,
)

# ── Folder setup ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
(ROOT / "outputs").mkdir(exist_ok=True)
(ROOT / "memory").mkdir(exist_ok=True)

BRIEFS_FILE = ROOT / "memory" / "daily_briefs.json"

# ── Agent instances ───────────────────────────────────────────────────────────

commission = CommissionAgent()
leads      = LeadMonitorAgent()
ecommerce  = EcommerceAgent()
video      = VideoPipelineAgent()
income     = IncomeGoalsAgent()
script     = VideoScriptAgent()

# Agents included in the full daily brief
ALL_AGENTS = [income, commission, leads, ecommerce, video, script]

# ── SMS helper ────────────────────────────────────────────────────────────────

_TELNYX_URL = "https://api.telnyx.com/v2/messages"


def _send_sms(body: str) -> None:
    """Send a message to YOUR_NUMBER via Telnyx."""
    api_key     = os.getenv("TELNYX_API_KEY")
    from_number = os.getenv("TELNYX_NUMBER")
    to_number   = os.getenv("YOUR_NUMBER")

    if not all([api_key, from_number, to_number]):
        print("[SMS] Telnyx credentials missing (TELNYX_API_KEY / TELNYX_NUMBER / YOUR_NUMBER) — skipping.")
        return

    # SMS segments cap at ~1600 chars; truncate gracefully
    if len(body) > 1600:
        body = body[:1597] + "..."

    try:
        resp = requests.post(
            _TELNYX_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"from": from_number, "to": to_number, "text": body},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"[SMS] Brief delivered to {to_number}")
    except Exception as e:
        print(f"[SMS] Send failed: {e}")


# ── Brief persistence ─────────────────────────────────────────────────────────


def _save_brief(brief: str) -> None:
    """Append the brief to memory/daily_briefs.json."""
    if BRIEFS_FILE.exists():
        with open(BRIEFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"briefs": []}

    data["briefs"].append({
        "timestamp": datetime.now().isoformat(),
        "brief": brief,
    })

    with open(BRIEFS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Core orchestration ────────────────────────────────────────────────────────


def run_all_agents() -> None:
    """Run every agent, build a Jarvis brief, SMS it, and persist it."""
    print(f"\n{'=' * 52}")
    print(f"  JARVIS FIRING — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'=' * 52}\n")

    results: dict[str, str] = {}
    for agent in ALL_AGENTS:
        print(f"[{datetime.now():%H:%M:%S}] Running {agent.name}...")
        try:
            results[agent.name] = agent.run()
        except Exception as e:
            results[agent.name] = f"{agent.name.upper()}\n  Error: {e}"
        print("  Done.")

    brief = build_daily_brief(agent_results=results)
    print("\n" + brief + "\n")

    _send_sms(brief)
    _save_brief(brief)
    print("Brief complete.\n")


# ── Scheduler helpers ─────────────────────────────────────────────────────────


def _threaded(fn):
    """Launch fn in a daemon thread so agents never block the scheduler."""
    threading.Thread(target=fn, daemon=True).start()


def _schedule_jobs() -> None:
    schedule.every().day.at("08:00").do(lambda: _threaded(run_all_agents))
    schedule.every(6).hours.do(lambda: _threaded(leads.run))
    schedule.every().monday.at("09:00").do(lambda: _threaded(commission.run))
    schedule.every().day.at("20:00").do(lambda: _threaded(video.run))


def _scheduler_loop() -> None:
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    _schedule_jobs()

    print("Jarvis online.")
    print("  08:00 daily     → all agents + SMS brief")
    print("  every 6 hours   → leads monitor")
    print("  Monday 09:00    → commission check")
    print("  20:00 daily     → video pipeline")
    print("  SMS webhook     → http://0.0.0.0:5000/sms")
    print("\nPress Ctrl+C to stop.\n")

    # SMS webhook server in daemon thread
    threading.Thread(target=start_sms_server, daemon=True).start()

    # Scheduler in daemon thread — main thread stays as the process anchor
    threading.Thread(target=_scheduler_loop, daemon=True).start()

    if "--now" in sys.argv:
        run_all_agents()
        return

    # Keep the process alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
