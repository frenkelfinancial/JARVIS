"""
email_report.py — sends the Jarvis daily brief as an HTML email via Gmail API.
"""
import base64
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gmail_auth import get_gmail_service

REPORT_EMAIL = os.getenv("REPORT_EMAIL", "jacef8778099@gmail.com")

_SECTION_COLORS = {
    "commission": "#4fc3f7",
    "income_goals": "#81c784",
    "lead_monitor": "#ffb74d",
    "ecommerce": "#ce93d8",
    "video_pipeline": "#f48fb1",
    "video_script": "#80cbc4",
}
_DEFAULT_COLOR = "#888"

_AGENT_LABELS = {
    "commission": "EMAIL INTEL",
    "income_goals": "INCOME & GOALS",
    "lead_monitor": "LEADS",
    "ecommerce": "ECOMMERCE",
    "video_pipeline": "VIDEO PIPELINE",
    "video_script": "VIDEO SCRIPT",
}


def _section_html(name: str, content: str) -> str:
    label = _AGENT_LABELS.get(name, name.upper())
    color = _SECTION_COLORS.get(name, _DEFAULT_COLOR)
    safe = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <div style="margin:24px 0;">
      <div style="color:{color};font-size:11px;letter-spacing:2px;font-weight:bold;
                  border-bottom:1px solid #222;padding-bottom:6px;margin-bottom:10px;">
        {label}
      </div>
      <pre style="margin:0;color:#ccc;font-size:13px;line-height:1.7;
                  white-space:pre-wrap;font-family:'Courier New',monospace;">{safe}</pre>
    </div>"""


def _build_html(agent_results: dict, jarvis_summary: str, period: str) -> str:
    now = datetime.now()
    date_str = now.strftime("%A, %B %d %Y  //  %I:%M %p").replace(" 0", " ")
    sections = "".join(_section_html(k, v) for k, v in agent_results.items() if v)

    safe_summary = jarvis_summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#0d0d0d;color:#e0e0e0;font-family:'Courier New',monospace;
             padding:32px;margin:0;max-width:700px;">

  <div style="border-bottom:1px solid #333;padding-bottom:16px;margin-bottom:24px;">
    <div style="color:#4fc3f7;font-size:20px;font-weight:bold;letter-spacing:3px;">
      JARVIS // {period.upper()}
    </div>
    <div style="color:#555;font-size:11px;margin-top:4px;">{date_str}</div>
  </div>

  <div style="background:#0f1a2e;border-left:3px solid #4fc3f7;padding:14px 18px;
              border-radius:4px;color:#b0c4de;font-size:14px;line-height:1.7;
              margin-bottom:8px;">
    {safe_summary}
  </div>

  <div style="color:#333;font-size:11px;margin-bottom:8px;">── AGENT REPORTS ──</div>

  {sections}

  <div style="color:#333;font-size:11px;margin-top:32px;border-top:1px solid #1a1a1a;
              padding-top:12px;">
    Jarvis Agent System &nbsp;|&nbsp; {now.strftime("%Y-%m-%d %H:%M")}
  </div>

</body>
</html>"""


def send_daily_email(agent_results: dict, jarvis_summary: str, period: str) -> None:
    to = REPORT_EMAIL
    subject = f"Jarvis {period} — {datetime.now().strftime('%a %b %d')}"
    html = _build_html(agent_results, jarvis_summary, period)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "me"
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service = get_gmail_service()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[Email] Brief sent to {to}")
    except Exception as e:
        print(f"[Email] Send failed: {e}")
