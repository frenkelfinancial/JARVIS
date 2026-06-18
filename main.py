"""
Jarvis — Daily Intelligence Orchestrator
Runs all agents at 9am and sends a consolidated brief via email.

Usage:
  1. Fill in .env with your credentials and goals
  2. pip install -r requirements.txt
  3. python main.py           (runs on schedule — keep the window open)
     python main.py --now     (fire immediately for testing)
"""
import os
import sys
import schedule
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agents import (
    CommissionAgent,
    VideoPipelineAgent,
    LeadMonitorAgent,
    EcommerceAgent,
    IncomeGoalsAgent,
)

AGENTS = [
    IncomeGoalsAgent(),
    CommissionAgent(),
    LeadMonitorAgent(),
    EcommerceAgent(),
    VideoPipelineAgent(),
]

AGENT_DESCRIPTIONS = {
    "income_goals":    "Tracks your monthly/annual premium and commission targets",
    "commission":      "Monitors policy commissions from Airtable or Google Sheets",
    "lead_monitor":    "Pulls new leads from HubSpot or GoHighLevel",
    "ecommerce":       "Reports on Shopify or WooCommerce orders and revenue",
    "video_pipeline":  "Pulls YouTube channel stats and recent video performance",
}


def run_all_agents() -> list[tuple[str, str]]:
    results = []
    for agent in AGENTS:
        print(f"[{datetime.now():%H:%M:%S}] Running {agent.name}...")
        try:
            output = agent.run()
        except Exception as e:
            output = f"{agent.name.upper()}\n  Error: {e}"
        results.append((agent.name, output))
        print(f"  Done.")
    return results


def build_brief(results: list[tuple[str, str]]) -> tuple[str, str]:
    now = datetime.now()
    date_str = now.strftime("%A, %B %d %Y")
    time_str = now.strftime("%I:%M %p")

    divider = "=" * 48

    # Plain-text version
    plain_lines = [
        f"JARVIS DAILY BRIEF",
        f"{date_str}  •  {time_str} Central",
        divider,
        "",
        "AI AGENTS RUNNING TODAY",
        divider,
    ]
    for name, _ in results:
        desc = AGENT_DESCRIPTIONS.get(name, "")
        status = "✓ Active"
        plain_lines.append(f"  {name.replace('_', ' ').title():<22} {status}  —  {desc}")

    plain_lines += ["", divider, ""]

    for _, output in results:
        plain_lines.append(output)
        plain_lines.append("")

    plain_lines += [
        divider,
        f"Sent by Jarvis  •  {now.strftime('%Y-%m-%d %H:%M')}",
    ]

    plain = "\n".join(plain_lines)

    # HTML version
    agent_rows = ""
    for name, _ in results:
        desc = AGENT_DESCRIPTIONS.get(name, "")
        agent_rows += (
            f"<tr>"
            f"<td style='padding:4px 10px 4px 0;font-weight:600;color:#1a1a2e;white-space:nowrap'>"
            f"{name.replace('_', ' ').title()}</td>"
            f"<td style='padding:4px 10px;color:#22c55e;font-weight:600'>✓ Active</td>"
            f"<td style='padding:4px 0;color:#555'>{desc}</td>"
            f"</tr>"
        )

    report_sections = ""
    for _, output in results:
        lines = output.split("\n")
        header = lines[0] if lines else ""
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        report_sections += f"""
        <div style='margin-bottom:20px;background:#f8f9fa;border-left:4px solid #1a1a2e;border-radius:4px;padding:14px 16px'>
          <div style='font-weight:700;font-size:13px;color:#1a1a2e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px'>{header}</div>
          <pre style='margin:0;font-family:monospace;font-size:13px;color:#333;white-space:pre-wrap'>{body.strip()}</pre>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style='margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'>
  <div style='max-width:600px;margin:24px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)'>

    <!-- Header -->
    <div style='background:#1a1a2e;padding:28px 28px 20px'>
      <div style='font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase;margin-bottom:4px'>Jarvis Daily Brief</div>
      <div style='font-size:22px;font-weight:700;color:#fff'>{date_str}</div>
      <div style='font-size:13px;color:#94a3b8;margin-top:4px'>{time_str} Central</div>
    </div>

    <!-- Agent roster -->
    <div style='padding:20px 28px 10px'>
      <div style='font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px'>AI Agents Running Today</div>
      <table style='border-collapse:collapse;width:100%;font-size:13px'>
        {agent_rows}
      </table>
    </div>

    <hr style='border:none;border-top:1px solid #e5e7eb;margin:4px 28px'>

    <!-- Reports -->
    <div style='padding:16px 28px 24px'>
      <div style='font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.8px;margin-bottom:14px'>Agent Reports</div>
      {report_sections}
    </div>

    <!-- Footer -->
    <div style='background:#f8f9fa;padding:14px 28px;border-top:1px solid #e5e7eb'>
      <div style='font-size:11px;color:#9ca3af'>Sent by Jarvis  •  {now.strftime("%Y-%m-%d %H:%M")}</div>
    </div>

  </div>
</body>
</html>"""

    return plain, html


def send_email(plain: str, html: str) -> bool:
    gmail_user = os.getenv("GMAIL_ADDRESS")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")
    to_email = os.getenv("EMAIL_TO")

    if not all([gmail_user, gmail_pass, to_email]):
        print("[EMAIL] Gmail credentials missing in .env — skipping email.")
        return False

    now = datetime.now()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Jarvis Daily Brief — {now.strftime('%b %d %Y')}"
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
        print(f"[EMAIL] Sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")
        return False


def daily_job():
    print(f"\n{'='*50}")
    print(f"  JARVIS FIRING — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*50}\n")

    results = run_all_agents()
    plain, html = build_brief(results)

    print("\n" + plain)
    send_email(plain, html)
    print("\nBrief complete.\n")


def main():
    brief_time = os.getenv("DAILY_BRIEF_TIME", "09:00")
    schedule.every().day.at(brief_time).do(daily_job)
    print(f"Jarvis scheduled — daily brief at {brief_time} local time.")
    print("Press Ctrl+C to stop.\n")

    if "--now" in sys.argv:
        daily_job()
        return

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
