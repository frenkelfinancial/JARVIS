#!/usr/bin/env python3
"""
Ecommerce Agent — JARVIS
Uses Claude (claude-sonnet-4-6) to brainstorm 3 trending Etsy print-on-demand
t-shirt ideas and generate full SEO listings. Saves to memory/ecommerce_memory.json.
Displays an isometric terminal dashboard when run directly.

Required env var:   ANTHROPIC_API_KEY
Optional env vars:  ETSY_API_KEY  ETSY_SHOP_ID  ETSY_SHIPPING_PROFILE_ID
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

# Allow `import memory_store` when invoked directly (root not automatically on sys.path)
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import memory_store

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich.align import Align
    from rich import box as rich_box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── Constants ────────────────────────────────────────────────────────────────

JARVIS_ROOT  = _ROOT
MEMORY_PATH  = JARVIS_ROOT / "memory" / "ecommerce_memory.json"

# Etsy taxonomy: Clothing > Men's Clothing > Shirts > T-Shirts
ETSY_TSHIRT_TAXONOMY_ID = 68887419

NICHES = ["car culture", "motivational", "insurance/hustle", "midwest lifestyle"]

COMBINED_PROMPT = """You are a top Etsy print-on-demand seller and SEO copywriter.

Brainstorm 3 trending t-shirt ideas across these niches: {niches}
Then write a complete Etsy listing for each one.

Return ONLY a JSON object with this exact shape, no other text:
{{
  "products": [
    {{
      "title": "SEO-optimized Etsy title (max 140 chars)",
      "niche": "niche name",
      "concept": "one sentence design concept",
      "description": "SEO description ~100 words — unisex material, gift idea, sizes S-3XL, satisfaction guarantee, 3-4 keyword phrases",
      "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
      "price": 27.99
    }}
  ]
}}

Prices $24.99-$34.99. Tags max 20 chars each. Make ideas specific and emotionally resonant."""


# ── Isometric Building ───────────────────────────────────────────────────────

_HEADER = r"""
      ╱▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔╲
     ╱            🤖  J A R V I S  —  E C O M M E R C E  H Q      ╲
    ▕━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━▏"""

_ROOMS = """\
    ▕  ╔═══════════════╗  ╔═══════════════╗  ╔═══════════════╗  ▏
    ▕  ║  💡 IDEA LAB  ║  ║  ✏️  STUDIO   ║  ║  📤 POST DOCK ║  ▏
    ▕  ║               ║  ║               ║  ║               ║  ▏
    ▕  ║   {r1:<7}     ║  ║   {r2:<7}     ║  ║   {r3:<7}     ║  ▏
    ▕  ╚═══════════════╝  ╚═══════════════╝  ╚═══════════════╝  ▏
     ╲━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╱"""

_ICONS = {
    "idle":   "🤖",
    "active": "⚡🤖",
    "done":   "✅🤖",
}

def _build_floor(states: dict) -> str:
    return _HEADER + "\n" + _ROOMS.format(
        r1=states.get("idea",  _ICONS["idle"]),
        r2=states.get("write", _ICONS["idle"]),
        r3=states.get("post",  _ICONS["idle"]),
    )


# ── Isometric Dashboard ──────────────────────────────────────────────────────

class IsometricDashboard:
    def __init__(self) -> None:
        self._states:   dict            = {"idea": _ICONS["idle"], "write": _ICONS["idle"], "post": _ICONS["idle"]}
        self._logs:     list[tuple]     = []
        self._listings: list[dict]      = []
        self._live:     "Live | None"   = None
        self._console   = Console()

    def set_robot(self, room: str, state: str) -> None:
        self._states[room] = _ICONS[state]

    def log(self, msg: str) -> None:
        self._logs.append((datetime.now().strftime("%H:%M:%S"), msg))
        if len(self._logs) > 8:
            self._logs.pop(0)

    def add_listing(self, listing: dict) -> None:
        self._listings.append(listing)

    def _table(self) -> Table:
        t = Table(
            title="📋  Generated Listings",
            box=rich_box.SIMPLE_HEAVY,
            title_style="bold magenta",
            header_style="bold white",
        )
        t.add_column("Title",  style="green",  max_width=44, no_wrap=True)
        t.add_column("Price",  style="yellow", justify="center", width=8)
        t.add_column("Status", justify="center", width=9)
        for lst in self._listings:
            title = lst.get("title", "—")
            t.add_row(
                title[:42] + ("…" if len(title) > 42 else ""),
                f"${lst.get('price', 0):.2f}",
                lst.get("status_icon", "⏳"),
            )
        return t

    def _compose(self) -> Panel:
        log_body = "\n".join(
            f"[dim]{ts}[/dim]  {msg}" for ts, msg in self._logs[-6:]
        ) or "[dim]Waiting for agent…[/dim]"

        layout = Layout()
        layout.split_column(
            Layout(Align.center(Text(_build_floor(self._states), style="bold cyan")), name="floor",  size=10),
            Layout(Align.center(self._table()),                                        name="table",  size=8),
            Layout(Panel(log_body, title="[bold]Activity Log[/bold]", border_style="dim", padding=(0, 1)), name="logs"),
        )
        return Panel(
            layout,
            title="[bold cyan]  JARVIS Ecommerce Agent[/bold cyan]",
            border_style="bright_cyan",
            box=rich_box.DOUBLE_EDGE,
            padding=(0, 1),
        )

    def start(self) -> None:
        self._live = Live(self._compose(), console=self._console, refresh_per_second=6)
        self._live.start()

    def refresh(self) -> None:
        if self._live:
            self._live.update(self._compose())

    def stop(self) -> None:
        if self._live:
            self._live.stop()


# ── Memory helpers ───────────────────────────────────────────────────────────

def _load_ecommerce_memory() -> dict:
    if MEMORY_PATH.exists():
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"listings": [], "last_updated": None}


def _save_ecommerce_memory(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Claude helpers ───────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    raw = re.sub(r"^```[a-z]*\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(match.group() if match else raw)


# ── Etsy API v3 ──────────────────────────────────────────────────────────────

def _post_etsy_draft(listing: dict, api_key: str, shop_id: str) -> tuple[bool, str]:
    url     = f"https://openapi.etsy.com/v3/application/shops/{shop_id}/listings"
    headers = {
        "x-api-key":     api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "quantity":    999,
        "title":       listing["title"][:140],
        "description": listing["description"],
        "price":       float(listing["price"]),
        "who_made":    "i_did",
        "when_made":   "made_to_order",
        "taxonomy_id": ETSY_TSHIRT_TAXONOMY_ID,
        "tags":        [t[:20].lower() for t in listing.get("tags", [])[:5]],
        "is_supply":   False,
        "state":       "draft",
        "type":        "physical",
    }
    shipping_id = os.getenv("ETSY_SHIPPING_PROFILE_ID")
    if shipping_id:
        payload["shipping_profile_id"] = int(shipping_id)

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return True, str(resp.json().get("listing_id", ""))
    except requests.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", "")
        except Exception:
            pass
        return False, f"HTTP {e.response.status_code}: {detail or str(e)}"
    except Exception as e:
        return False, str(e)


# ── EcommerceAgent ───────────────────────────────────────────────────────────

class EcommerceAgent:
    """JARVIS agent — orchestrated by main.py. run() returns a plain string."""

    name = "ecommerce"

    def __init__(self, dash: IsometricDashboard | None = None) -> None:
        self._dash = dash
        self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY

    # ── internal helpers ──────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self._dash:
            self._dash.log(msg)
            self._dash.refresh()
        else:
            print(f"  {datetime.now().strftime('%H:%M:%S')}  {msg}")

    def _claude(self, prompt: str) -> str:
        resp = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    # ── pipeline steps ────────────────────────────────────────────────────

    def _brainstorm_and_generate(self) -> list[dict]:
        """Single Claude call: 3 ideas + full listings in one shot."""
        self._log("🧠  Generating 3 listings in one call…")
        if self._dash:
            self._dash.set_robot("idea", "active")
            self._dash.set_robot("write", "active")
            self._dash.refresh()

        raw      = self._claude(COMBINED_PROMPT.format(niches=", ".join(NICHES)))
        products = _parse_json(raw).get("products", [])[:3]

        if self._dash:
            self._dash.set_robot("idea", "done")
            self._dash.set_robot("write", "done")
            self._dash.refresh()

        self._log(f"✅  Got {len(products)} listings")
        return products

    def _upload(self, listing: dict, etsy_key: str, etsy_shop_id: str) -> dict:
        self._log(f"📡  Posting to Etsy: {listing.get('title', '')[:38]}…")
        if self._dash:
            self._dash.set_robot("post", "active")
            self._dash.refresh()

        success, detail = _post_etsy_draft(listing, etsy_key, etsy_shop_id)

        if self._dash:
            self._dash.set_robot("post", "done" if success else "idle")
            self._dash.refresh()

        if success:
            self._log(f"🚀  Uploaded! Etsy ID: {detail}")
            return {"status": "uploaded", "status_icon": "✅", "etsy_listing_id": detail}
        else:
            self._log(f"⚠️   Upload failed: {detail}")
            return {"status": "upload_failed", "status_icon": "⚠️", "upload_error": detail}

    # ── public entry point ────────────────────────────────────────────────

    def run(self) -> str:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "ETSY AGENT\n  Skipped — ANTHROPIC_API_KEY not set in .env"

        etsy_key     = os.getenv("ETSY_API_KEY")
        etsy_shop_id = os.getenv("ETSY_SHOP_ID")
        use_etsy     = bool(etsy_key and etsy_shop_id)
        timestamp    = datetime.now().isoformat()

        try:
            products = self._brainstorm_and_generate()
        except Exception as exc:
            msg = f"ETSY AGENT\n  Claude call failed: {exc}"
            memory_store.update_agent(self.name, msg)
            return msg

        listings  = []
        uploaded  = 0
        pending   = 0
        titles    = []

        for product in products:
            listing = dict(product)
            listing["generated_at"] = timestamp

            if use_etsy:
                result = self._upload(listing, etsy_key, etsy_shop_id)
                listing.update(result)
                if result["status"] == "uploaded":
                    uploaded += 1
                else:
                    listing["status"] = "pending"
                    pending += 1
            else:
                listing["status"]      = "pending"
                listing["status_icon"] = "📁"
                pending += 1

            listings.append(listing)
            titles.append(listing.get("title", "Untitled"))

            if self._dash:
                self._dash.add_listing(listing)
                self._dash.refresh()

            time.sleep(0.3)

        # Persist to ecommerce-specific memory file
        mem = _load_ecommerce_memory()
        mem.setdefault("listings", []).extend(listings)
        _save_ecommerce_memory(mem)
        self._log(f"💾  Saved to {MEMORY_PATH.name}")

        # Build summary string
        titles_str = ", ".join(f"'{t[:28]}'" for t in titles)
        if use_etsy:
            status_str = f"{uploaded} uploaded, {pending} pending"
        else:
            status_str = f"{pending} saved locally — ready to upload manually"

        summary = (
            f"ETSY AGENT\n"
            f"  {len(listings)} new Etsy listings drafted: {titles_str}. "
            f"{status_str}."
        )

        memory_store.update_agent(
            self.name, summary,
            {"listings_generated": len(listings), "uploaded": uploaded, "pending": pending},
        )
        return summary


# ── Module-level run() — used when executing directly ────────────────────────

def run() -> str:
    """Generate 3 Etsy listings with a live isometric dashboard. Returns summary."""
    if HAS_RICH:
        dash  = IsometricDashboard()
        agent = EcommerceAgent(dash)
        try:
            dash.start()
            dash.log("🚀  JARVIS Ecommerce Agent starting…")
            dash.refresh()
            time.sleep(0.4)
            summary = agent.run()
            dash.log(f"🎉  Done!")
            dash.refresh()
            time.sleep(4)
        finally:
            dash.stop()
        Console().print(f"\n[bold green]✅  Summary:[/bold green] {summary}\n")
    else:
        agent   = EcommerceAgent()
        summary = agent.run()
        print(f"\n✅  {summary}\n")
    return summary


if __name__ == "__main__":
    run()
