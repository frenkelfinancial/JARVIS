import os
import sys
import base64
import tempfile
import requests
from flask import Flask, request, jsonify, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))

from agents import CommissionAgent, LeadMonitorAgent, EcommerceAgent, VideoPipelineAgent
from jarvis import ask_jarvis, build_daily_brief

app = Flask(__name__)

TELNYX_API_URL = "https://api.telnyx.com/v2/messages"
_HERE = os.path.dirname(os.path.abspath(__file__))

_commission_agent = CommissionAgent()
_leads_agent      = LeadMonitorAgent()
_video_agent      = VideoPipelineAgent()
_ecommerce_agent  = EcommerceAgent()

# ── Whisper singleton (lazy-loaded on first /voice call) ──────────────────────
_whisper = None

def _get_whisper():
    global _whisper
    if _whisper is None:
        os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _whisper

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    return send_from_directory(_HERE, "dashboard.html")

# ── Voice chat endpoint ───────────────────────────────────────────────────────
@app.route("/voice", methods=["POST"])
def voice_chat():
    audio = request.files.get("audio")
    if not audio:
        return jsonify({"error": "no audio"}), 400

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        audio.save(f.name)
        tmp = f.name

    try:
        model   = _get_whisper()
        segs, _ = model.transcribe(tmp, language="en")
        text    = " ".join(s.text for s in segs).strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try: os.unlink(tmp)
        except Exception: pass

    if not text:
        return jsonify({"text": "", "reply": "", "audio": None})

    reply = ask_jarvis(text)

    audio_b64 = None
    api_key  = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    if api_key:
        try:
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json={"text": reply, "model_id": "eleven_turbo_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
                timeout=20,
            )
            if resp.ok:
                audio_b64 = base64.b64encode(resp.content).decode()
        except Exception:
            pass

    return jsonify({"text": text, "reply": reply, "audio": audio_b64})

# ── SMS helper ────────────────────────────────────────────────────────────────
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

# ── SMS webhook ───────────────────────────────────────────────────────────────
@app.route("/sms", methods=["POST"])
def sms_webhook():
    data = request.get_json(force=True)

    try:
        payload     = data["data"]["payload"]
        from_number = payload["from"]["phone_number"]
        body        = payload["text"].strip()
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
            "leads":       _leads_agent.run(),
            "video":       _video_agent.run(),
            "ecommerce":   _ecommerce_agent.run(),
        }
        reply = build_daily_brief(agent_results)
    else:
        reply = ask_jarvis(body)

    if len(reply) > 1600:
        reply = reply[:1597] + "..."

    _send_sms(from_number, reply)
    return jsonify({"status": "ok"}), 200


def start_sms_server():
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    start_sms_server()
