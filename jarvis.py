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


def synthesize_brief(agent_results: dict, period: str) -> str:
    """Feed all agent outputs to Jarvis and get a 3-5 sentence narrative synthesis."""
    context = "\n\n".join(
        f"[{k.upper()}]\n{v}" for k, v in agent_results.items() if v
    )
    prompt = (
        f"It's your {period}. Here's everything your agents just reported:\n\n"
        f"{context}\n\n"
        "Give Jace a tight 3-5 sentence take: what's most important right now, "
        "anything urgent to handle, and one clear action. Direct. No filler. JARVIS mode."
    )
    try:
        return ask_jarvis(prompt)
    except Exception as e:
        return f"[Jarvis synthesis unavailable: {e}]"


def build_daily_brief(agent_results={}):
    """Plain-text brief for persistence — concatenates all agent outputs."""
    from datetime import datetime
    header = "JARVIS BRIEF -- " + datetime.now().strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
    if agent_results:
        sections = [v for v in agent_results.values() if v]
        body = "\n\n".join(sections)
    else:
        body = "No agent data available."
    return f"{header}\n{'─' * 30}\n{body}"
