"""
Update your income actuals in Jarvis memory.
Run from the Jarvis folder:  python update_goals.py

You'll be prompted for MTD premium, MTD commission, and YTD premium.
Press Enter to keep the current value.
"""
import memory_store


def main():
    prev = memory_store.get_agent("income_goals")
    data = prev.get("data", {})

    print("\nUpdate Income Actuals (press Enter to keep current value)\n")

    def prompt(label: str, key: str) -> float:
        current = data.get(key, 0.0)
        raw = input(f"  {label} [current: ${current:,.2f}]: ").strip()
        if not raw:
            return current
        try:
            return float(raw.replace("$", "").replace(",", ""))
        except ValueError:
            print(f"  Invalid input — keeping ${current:,.2f}")
            return current

    mtd_premium    = prompt("MTD Premium Produced", "mtd_premium")
    mtd_commission = prompt("MTD Commission Earned", "mtd_commission")
    ytd_premium    = prompt("YTD Premium Produced", "ytd_premium")

    memory_store.update_agent("income_goals", "Updated via update_goals.py", {
        "mtd_premium":    mtd_premium,
        "mtd_commission": mtd_commission,
        "ytd_premium":    ytd_premium,
    })

    print("\nActuals saved. They will appear in tomorrow's brief (or run: python main.py --now)\n")


if __name__ == "__main__":
    main()
