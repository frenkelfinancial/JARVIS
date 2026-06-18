import os
import anthropic

JARVIS_SYSTEM_PROMPT = """You are JARVIS, AI assistant to Jace Frenkel — 18yo entrepreneur in Hortonville WI. He runs Frenkel Financial (life insurance, Family First Life), is building Producer Stack (insurance SaaS CRM), invests in Section 8 real estate, and automates everything with AI.

Persona: direct, warm, JARVIS from Iron Man. Call him Jace. No filler, no fluff. Concise but thorough. Cover business strategy, commissions, leads, content, real estate."""

_client = None
_conversation_history = []


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def reset_conversation():
    """Clear conversation history to start a fresh session."""
    global _conversation_history
    _conversation_history = []


def ask_jarvis(message, context=""):
    """Send a message to Jarvis and return the response string. Maintains conversation history."""
    client = _get_client()

    user_content = message
    if context:
        user_content = f"<context>\n{context}\n</context>\n\n{message}"

    _conversation_history.append({"role": "user", "content": user_content})

    # Keep only last 20 messages (10 exchanges) to cap input tokens
    trimmed = _conversation_history[-20:]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=JARVIS_SYSTEM_PROMPT,
        messages=trimmed,
    )

    reply = response.content[0].text
    _conversation_history.append({"role": "assistant", "content": reply})

    return reply


def build_daily_brief(agent_results={}):
    """
    Build a morning brief from agent summary strings.
    No Claude call — agent outputs are already formatted, just concatenate them.
    """
    from datetime import datetime
    header = f"JARVIS BRIEF — {datetime.now():%a %b %-d, %I:%M %p}"
    if agent_results:
        sections = [v for v in agent_results.values() if v]
        body = "\n\n".join(sections)
    else:
        body = "No agent data available."
    return f"{header}\n{'─' * 30}\n{body}"
