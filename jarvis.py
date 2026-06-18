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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=JARVIS_SYSTEM_PROMPT,
        messages=_conversation_history,
    )

    reply = response.content[0].text
    _conversation_history.append({"role": "assistant", "content": reply})

    return reply


def build_daily_brief(agent_results={}):
    """
    Build a morning brief from a dict of agent summary strings.
    Keys are agent names, values are summary strings returned by agent.run().
    Returns the formatted brief string.
    """
    if agent_results:
        sections = []
        for agent_name, summary in agent_results.items():
            sections.append(f"[{agent_name.upper()}]\n{summary}")
        context = "\n\n".join(sections)
    else:
        context = "No agent data available for this brief."

    message = (
        "Good morning, Jace. Format the agent reports below into a clean, concise morning brief. "
        "Lead with anything that needs immediate attention, then quick status on each area. "
        "Keep it sharp — no padding."
    )

    return ask_jarvis(message, context=context)
