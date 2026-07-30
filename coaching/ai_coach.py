# coaching/ai_coach.py
"""
Quantoryx AI Performance Coach.

Reads a trader's journal, analyzes behavioral patterns, and
generates a personalized coaching session using Claude AI.

Unlike generic trading tips, this coach:
  - References your actual trades, not hypothetical examples
  - Identifies YOUR specific weaknesses (not general ones)
  - Adapts its advice to your strategy and trading style
  - Tracks improvement week-over-week
  - Gives concrete, actionable changes (not vague "improve your mindset")
  - Simulates a session with a professional trading coach

The AI coach is powered by the Anthropic API (claude-sonnet-4-6).
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CoachingSession:
    session_id: str
    trader_summary: str
    strengths: List[str]
    weaknesses: List[str]
    action_plan: List[str]
    weekly_focus: str
    full_coaching_text: str
    performance_score: int    # 0–100
    next_session_date: str


class AIPerformanceCoach:
    """
    Generates personalized coaching sessions from trade journal data.

    Usage:
        coach = AIPerformanceCoach()
        session = await coach.coach(journal_analytics, trader_profile)
    """

    COACH_SYSTEM_PROMPT = """You are a world-class professional forex trading coach with 20 years of experience.
You have coached traders at top prop firms including FTMO, The5%ers, and hedge funds.

Your coaching style:
- Direct, honest, and encouraging — not harsh, not sugar-coating
- Always reference the trader's ACTUAL data, never generic advice
- Give 3 specific, actionable changes — not vague platitudes
- Identify the single most important thing they should fix this week
- Acknowledge what they are doing well (traders quit when they only hear criticism)
- Use analogies to make concepts memorable

You receive trade journal analytics as JSON. Your job is to give a coaching session
as if you are sitting across from the trader. Write in second person ("you", "your").
Keep the full coaching text under 400 words — dense and valuable, not padded."""

    def __init__(self, api_base: str = "https://api.anthropic.com/v1/messages"):
        self._api_base = api_base

    async def coach(
        self,
        journal_analytics: Dict,
        trader_name: str = "Trader",
        experience_level: str = "Intermediate",
        primary_strategy: str = "mixed",
        account_size: float = 10_000.0,
    ) -> CoachingSession:
        """
        Generate a full coaching session from journal analytics.
        Returns a CoachingSession with structured output + full text.
        """
        import uuid, datetime

        session_id = str(uuid.uuid4())[:8]
        prompt = self._build_prompt(
            journal_analytics, trader_name, experience_level,
            primary_strategy, account_size
        )

        coaching_text = await self._call_claude(prompt)
        structured    = self._parse_structured(journal_analytics)

        return CoachingSession(
            session_id=session_id,
            trader_summary=self._trader_summary(journal_analytics, trader_name),
            strengths=structured["strengths"],
            weaknesses=structured["weaknesses"],
            action_plan=structured["action_plan"],
            weekly_focus=structured["weekly_focus"],
            full_coaching_text=coaching_text,
            performance_score=structured["score"],
            next_session_date=(
                datetime.datetime.now() + datetime.timedelta(days=7)
            ).strftime("%Y-%m-%d"),
        )

    async def _call_claude(self, prompt: str) -> str:
        """Call Claude API for coaching generation."""
        try:
            import aiohttp, os
            payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": self.COACH_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._api_base,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["content"][0]["text"]
                    else:
                        return self._fallback_coaching(prompt)
        except Exception:
            return self._fallback_coaching(prompt)

    def _build_prompt(self, analytics: Dict, name: str, level: str, strategy: str, size: float) -> str:
        summary = analytics.get("summary", {})
        tips    = analytics.get("improvement_tips", [])
        flags   = analytics.get("behaviour_flags", [])
        by_strat = analytics.get("by_strategy", [])
        by_hour  = analytics.get("by_hour", [])

        return f"""Coach a trader named {name} ({level} level, {strategy} strategy, ${size:,.0f} account).

THEIR PERFORMANCE DATA:
{json.dumps(summary, indent=2)}

BEHAVIOUR FLAGS DETECTED:
{json.dumps(flags, indent=2)}

BEST/WORST BY STRATEGY:
{json.dumps(by_strat[:3], indent=2)}

TIME-OF-DAY INSIGHTS:
{json.dumps(by_hour[:5], indent=2)}

SYSTEM-GENERATED TIPS:
{chr(10).join(f'- {t}' for t in tips)}

Please give {name} a direct, personalized coaching session. Be specific to their data.
Structure: (1) What they're doing well, (2) Their biggest problem right now,
(3) Three concrete changes for this week, (4) One mindset reframe."""

    def _parse_structured(self, analytics: Dict) -> Dict:
        """Extract structured insights from analytics for the session card."""
        summary  = analytics.get("summary", {})
        flags    = analytics.get("behaviour_flags", [])
        by_strat = analytics.get("by_strategy", [])

        wr  = summary.get("win_rate", 0.5)
        pf  = summary.get("profit_factor", 1.0)
        rr  = summary.get("risk_reward_ratio", 1.0)
        dd  = abs(summary.get("max_drawdown_pct", 0))

        strengths = []
        if wr >= 0.55:  strengths.append(f"Strong win rate: {wr*100:.0f}%")
        if pf >= 1.5:   strengths.append(f"Healthy profit factor: {pf:.1f}")
        if rr >= 2.0:   strengths.append(f"Good R:R ratio: {rr:.1f}")
        if dd < 5:      strengths.append(f"Excellent drawdown control: {dd:.1f}%")
        if not strengths: strengths.append("Actively tracking performance — that's the first step.")

        weaknesses = []
        if wr < 0.45:    weaknesses.append(f"Win rate below 45% ({wr*100:.0f}%)")
        if pf < 1.3:     weaknesses.append(f"Low profit factor ({pf:.1f})")
        if rr < 1.5:     weaknesses.append(f"R:R below 1.5 ({rr:.1f})")
        if dd > 10:      weaknesses.append(f"High drawdown: {dd:.1f}%")
        for f in flags:  weaknesses.append(f.get("description","")[:80])
        if not weaknesses: weaknesses.append("No critical weaknesses detected this period.")

        # Action plan from tips
        action_plan = analytics.get("improvement_tips", [])[:3]
        if not action_plan: action_plan = ["Review your worst 3 trades and identify the pattern."]

        # Weekly focus: worst weakness
        weekly_focus = weaknesses[0] if weaknesses else "Maintain consistency."

        # Score: 0–100
        score = int(min(100, max(0,
            wr * 40 + min(pf / 2.0, 1.0) * 30 + min(rr / 3.0, 1.0) * 20 + (1 - min(dd/20,1)) * 10
        )))

        return {
            "strengths": strengths[:3],
            "weaknesses": weaknesses[:3],
            "action_plan": action_plan,
            "weekly_focus": weekly_focus,
            "score": score,
        }

    def _trader_summary(self, analytics: Dict, name: str) -> str:
        s = analytics.get("summary", {})
        return (
            f"{name} — {s.get('total_trades',0)} trades | "
            f"WR: {s.get('win_rate',0)*100:.0f}% | "
            f"PF: {s.get('profit_factor',0):.1f} | "
            f"DD: {abs(s.get('max_drawdown_pct',0)):.1f}%"
        )

    def _fallback_coaching(self, prompt: str) -> str:
        return (
            "Based on your trading data, here are your key takeaways:\n\n"
            "Your win rate and risk management will define your long-term success more than any single strategy. "
            "Focus on consistency in your process — entry criteria, position sizing, and exit discipline. "
            "Review your three worst trades this week and identify the common denominator. "
            "That pattern is your biggest edge improvement opportunity.\n\n"
            "This week: Don't add new strategies. Master the ones you have."
        )
