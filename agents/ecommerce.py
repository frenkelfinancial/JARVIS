"""
Ecommerce Agent
Supports: Shopify  OR  WooCommerce
Shopify:     set SHOPIFY_STORE_DOMAIN + SHOPIFY_ACCESS_TOKEN
WooCommerce: set WOOCOMMERCE_URL + WOOCOMMERCE_CONSUMER_KEY + WOOCOMMERCE_CONSUMER_SECRET
"""
import os
import requests
from datetime import datetime, timedelta, timezone
import memory_store


class EcommerceAgent:
    name = "ecommerce"

    def run(self) -> str:
        try:
            if os.getenv("SHOPIFY_ACCESS_TOKEN"):
                return self._run_shopify()
            elif os.getenv("WOOCOMMERCE_CONSUMER_KEY"):
                return self._run_woo()
            else:
                return self._no_creds()
        except Exception as e:
            msg = f"Ecommerce Agent error: {e}"
            memory_store.update_agent(self.name, msg)
            return msg

    # ── Shopify ───────────────────────────────────────────────

    def _run_shopify(self) -> str:
        domain = os.environ["SHOPIFY_STORE_DOMAIN"]
        token = os.environ["SHOPIFY_ACCESS_TOKEN"]
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S%z")

        resp = requests.get(
            f"https://{domain}/admin/api/2024-01/orders.json",
            headers=headers,
            params={"status": "any", "created_at_min": since, "limit": 250},
            timeout=15,
        )
        resp.raise_for_status()
        orders = resp.json().get("orders", [])

        revenue = sum(float(o.get("total_price", 0)) for o in orders)
        refunds = sum(float(o.get("total_price", 0)) for o in orders if o.get("financial_status") == "refunded")
        pending = [o for o in orders if o.get("fulfillment_status") is None]

        summary = (
            f"ECOMMERCE (24h via Shopify)\n"
            f"  Orders: {len(orders)}\n"
            f"  Revenue: ${revenue:,.2f}\n"
            f"  Refunds: ${refunds:,.2f}\n"
            f"  Unfulfilled: {len(pending)}"
        )
        memory_store.update_agent(self.name, summary, {"orders": len(orders), "revenue": revenue})
        return summary

    # ── WooCommerce ───────────────────────────────────────────

    def _run_woo(self) -> str:
        base_url = os.environ["WOOCOMMERCE_URL"].rstrip("/")
        ck = os.environ["WOOCOMMERCE_CONSUMER_KEY"]
        cs = os.environ["WOOCOMMERCE_CONSUMER_SECRET"]
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

        resp = requests.get(
            f"{base_url}/wp-json/wc/v3/orders",
            auth=(ck, cs),
            params={"after": since, "per_page": 100, "status": "any"},
            timeout=15,
        )
        resp.raise_for_status()
        orders = resp.json()

        revenue = sum(float(o.get("total", 0)) for o in orders if o.get("status") not in ("refunded", "cancelled"))
        pending = [o for o in orders if o.get("status") == "processing"]

        summary = (
            f"ECOMMERCE (24h via WooCommerce)\n"
            f"  Orders: {len(orders)}\n"
            f"  Revenue: ${revenue:,.2f}\n"
            f"  Processing: {len(pending)}"
        )
        memory_store.update_agent(self.name, summary, {"orders": len(orders), "revenue": revenue})
        return summary

    # ── No credentials ────────────────────────────────────────

    def _no_creds(self) -> str:
        prev = memory_store.get_agent(self.name)
        prev_rev = prev.get("data", {}).get("revenue", 0)
        msg = (
            f"ECOMMERCE\n"
            f"  [Demo mode — set SHOPIFY_ACCESS_TOKEN or WOOCOMMERCE_CONSUMER_KEY in .env]\n"
            f"  Last recorded revenue: ${prev_rev:,.2f}"
        )
        memory_store.update_agent(self.name, msg)
        return msg
