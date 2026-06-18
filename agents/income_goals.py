"""
Income Goals Agent
Tracks MTD and YTD premium/commission progress against configured targets.
Set MONTHLY_PREMIUM_GOAL, MONTHLY_COMMISSION_GOAL, ANNUAL_PREMIUM_GOAL in .env.
Update MTD/YTD actuals by calling memory_store.update_agent("income_goals", ...) from
another script or manually via update_goals.py.
"""
import os
import calendar
from datetime import date
import memory_store


class IncomeGoalsAgent:
    name = "income_goals"

    def run(self) -> str:
        try:
            today = date.today()
            days_in_month = calendar.monthrange(today.year, today.month)[1]
            days_elapsed = today.day
            days_remaining = days_in_month - days_elapsed + 1

            monthly_premium_goal = float(os.getenv("MONTHLY_PREMIUM_GOAL", "0"))
            monthly_commission_goal = float(os.getenv("MONTHLY_COMMISSION_GOAL", "0"))
            annual_premium_goal = float(os.getenv("ANNUAL_PREMIUM_GOAL", "0"))

            prev = memory_store.get_agent(self.name)
            data = prev.get("data", {})
            mtd_premium = float(data.get("mtd_premium", 0))
            mtd_commission = float(data.get("mtd_commission", 0))
            ytd_premium = float(data.get("ytd_premium", 0))

            lines = [f"INCOME & GOALS — {today.strftime('%B %Y')}"]

            if monthly_premium_goal > 0:
                pct = (mtd_premium / monthly_premium_goal * 100)
                gap = monthly_premium_goal - mtd_premium
                daily_pace = gap / days_remaining if days_remaining > 0 else 0
                bar = self._progress_bar(pct)
                lines += [
                    f"  Premium Goal:      ${monthly_premium_goal:,.0f}/mo",
                    f"  MTD Production:    ${mtd_premium:,.2f} {bar} {pct:.1f}%",
                    f"  Gap to goal:       ${gap:,.2f} ({days_remaining} days left)",
                    f"  Daily pace needed: ${daily_pace:,.2f}/day",
                ]
            else:
                lines.append("  [Set MONTHLY_PREMIUM_GOAL in .env to track premium targets]")

            if monthly_commission_goal > 0:
                pct_c = (mtd_commission / monthly_commission_goal * 100)
                gap_c = monthly_commission_goal - mtd_commission
                bar_c = self._progress_bar(pct_c)
                lines += [
                    f"  Commission Goal:   ${monthly_commission_goal:,.0f}/mo",
                    f"  MTD Commission:    ${mtd_commission:,.2f} {bar_c} {pct_c:.1f}%",
                    f"  Commission gap:    ${gap_c:,.2f}",
                ]

            if annual_premium_goal > 0:
                pct_a = (ytd_premium / annual_premium_goal * 100)
                months_done = today.month - 1 + (today.day / days_in_month)
                expected_ytd = (annual_premium_goal / 12) * months_done
                pace_status = "AHEAD" if ytd_premium >= expected_ytd else "BEHIND"
                lines += [
                    f"  Annual Goal:       ${annual_premium_goal:,.0f}",
                    f"  YTD Production:    ${ytd_premium:,.2f} ({pct_a:.1f}%) — {pace_status} of pace",
                ]

            summary = "\n".join(lines)
            memory_store.update_agent(self.name, summary, {
                "mtd_premium": mtd_premium,
                "mtd_commission": mtd_commission,
                "ytd_premium": ytd_premium,
            })
            return summary

        except Exception as e:
            msg = f"Income Goals Agent error: {e}"
            memory_store.update_agent(self.name, msg)
            return msg

    def _progress_bar(self, pct: float, width: int = 10) -> str:
        filled = min(int(pct / 100 * width), width)
        return f"[{'#' * filled}{'.' * (width - filled)}]"
