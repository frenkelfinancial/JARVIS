import os
import sys
import requests
from flask import Flask, request, jsonify

# Allow running from the Jarvis root without installing as a package
sys.path.insert(0, os.path.dirname(__file__))

from agents import CommissionAgent, LeadMonitorAgent, EcommerceAgent, VideoPipelineAgent
from jarvis import ask_jarvis, build_daily_brief

app = Flask(__name__)

TELNYX_API_URL = "https://api.telnyx.com/v2/messages"

# Instantiate once at startup — agents hold no long-lived state
_commission_agent = CommissionAgent()
_leads_agent = LeadMonitorAgent()
_video_agent = VideoPipelineAgent()
_ecommerce_agent = EcommerceAgent()


def _send_sms(to_number, body):
    headers = {
        "Authorization": f"Bearer {os.environ['TELNYX_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": os.environ["TELNYX_NUMBER"],
        "to": to_number,
        "text": body,
    }
    resp = requests.post(TELNYX_API_URL, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


@app.route("/sms", methods=["POST"])
def sms_webhook():
    data = request.get_json(force=True)

    try:
        payload = data["data"]["payload"]
        from_number = payload["from"]["phone_number"]
        body = payload["text"].strip()
    except (KeyError, TypeError):
        return jsonify({"error": "invalid payload"}), 400

    text = body.lower()

    if any(kw in text for kw in ("commission", "chargeback")):
        reply = _commission_agent.run()

    elif any(kw in text for kw in ("lead", "pipeline")):
        reply = _leads_agent.run()

    elif any(kw in text for kw in ("video", "content", "post")):
        reply = _video_agent.run()

    elif any(kw in text for kw in ("etsy", "listing", "shop")):
        reply = _ecommerce_agent.run()

    elif any(kw in text for kw in ("brief", "update", "morning")):
        agent_results = {
            "commissions": _commission_agent.run(),
            "leads": _leads_agent.run(),
            "video": _video_agent.run(),
            "ecommerce": _ecommerce_agent.run(),
        }
        reply = build_daily_brief(agent_results)

    else:
        reply = ask_jarvis(body)

    # Truncate to ~10 SMS segments to avoid runaway messages
    if len(reply) > 1600:
        reply = reply[:1597] + "..."

    _send_sms(from_number, reply)
    return jsonify({"status": "ok"}), 200


def start_sms_server():
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    start_sms_server()
