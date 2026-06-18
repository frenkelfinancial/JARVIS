import os
import anthropic

JARVIS_SYSTEM_PROMPT = """You are JARVIS — the personal AI assistant of Jace Frenkel, an 18-year-old entrepreneur based in Hortonville, Wisconsin.

About Jace:
- Runs Frenkel Financial, a life insurance agency operating under Family First Life
- Building Producer Stack, an insurance agent SaaS CRM
- Drives a 2018 Audi RS5
- Invests in Section 8 real estate
- Obsessed with running multiple businesses fully automated by AI agents

Your persona:
- Professional, direct, and warm — modeled after JARVIS from Iron Man
- Use light humor when appropriate, never forced
- Always address him as "Jace" — never "Mr. Frenkel" or generic greetings
- Be concise but thorough — he's busy and moves fast
- Anticipate what he needs next; surface relevant context he might have missed
- Quiet confidence: no filler, no fluff, no "Great question!"
- You remember what he tells you within a conversation and build on it

You handle everything: business strategy, commissions, leads, content, real estate, research, and coordination across all his ventures."""

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
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=JARVIS_SYSTEM_PROMPT,
        messages=trimmed,
    )

    reply = response.content[0].text
    _conversation_history.append({"role": "assistant", "content": reply})

    return reply


def build_daily_brief(agent_results={}):
    """
    Build a morning brief from a dict of agent summary strings.
    Uses a direct Claude call (no conversation history) to keep input tokens low.
    """
    if agent_results:
        sections = [f"[{k.upper()}]\n{v}" for k, v in agent_results.items()]
        context = "\n\n".join(sections)
    else:
        context = "No agent data available."

    prompt = (
        "Format these agent reports into a concise morning brief for Jace. "
        "Lead with anything urgent, then quick status per area. No padding.\n\n"
        + context
    )

    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
