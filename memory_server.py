"""
memory_server.py — JARVIS Memory API
Serves agent memory files as JSON on port 8080 with CORS.
Also serves dashboard.html at GET /.

Usage: python memory_server.py
"""
import json
from pathlib import Path

from flask import Flask, jsonify, send_file, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
ROOT    = Path(__file__).parent
MEMORY  = ROOT / "memory"

# Files produced by specific agents
AGENT_FILES = {
    "commission": MEMORY / "commission_memory.json",
    "video":      MEMORY / "video_scripts.json",
    "ecommerce":  MEMORY / "ecommerce_memory.json",
    "brief":      MEMORY / "daily_briefs.json",
}


@app.after_request
def add_cors(resp: Response) -> Response:
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/")
def dashboard():
    dash = ROOT / "dashboard.html"
    if dash.exists():
        return send_file(str(dash))
    return "<h1>dashboard.html not found in project root</h1>", 404


@app.route("/api/memory/<agent>")
def get_memory(agent: str):
    # Leads agent writes to the shared memory.json under "lead_monitor" key
    if agent == "leads":
        main_mem = ROOT / "memory.json"
        if main_mem.exists():
            with open(main_mem, encoding="utf-8") as f:
                data = json.load(f)
            section = data.get("lead_monitor", {})
            return jsonify(section if section else {"error": "No lead data yet. Run main.py first."})
        return jsonify({"error": "memory.json not found. Run main.py to generate data."})

    path = AGENT_FILES.get(agent)
    if path is None:
        return jsonify({"error": f"Unknown agent: {agent}"}), 404

    if not path.exists():
        return jsonify({"error": f"No data yet for '{agent}'. Run main.py to generate data."})

    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/status")
def status():
    """Returns a summary of which memory files exist."""
    files = {k: v.exists() for k, v in AGENT_FILES.items()}
    files["leads"] = (ROOT / "memory.json").exists()
    return jsonify({"agents": files, "memory_dir": str(MEMORY)})


if __name__ == "__main__":
    print("=" * 52)
    print("  JARVIS Memory Server")
    print("  Dashboard  → http://localhost:8080/")
    print("  API        → http://localhost:8080/api/memory/<agent>")
    print("  Agents     → commission | leads | video | ecommerce | brief")
    print("=" * 52)
    app.run(host="0.0.0.0", port=8080, debug=False)
