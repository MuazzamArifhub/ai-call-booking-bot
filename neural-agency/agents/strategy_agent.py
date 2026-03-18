"""
Strategy Agent - Analyzes the client brief and produces a comprehensive campaign strategy.
Uses Claude to think like a senior marketing strategist.
"""

import anthropic
from typing import AsyncGenerator


async def run_strategy_agent(
    client: anthropic.AsyncAnthropic,
    brief: dict,
) -> str:
    """
    Generate a full marketing campaign strategy from a client brief.
    Returns structured strategy as markdown.
    """
    system_prompt = """You are a senior marketing strategist at a world-class agency with 20 years of experience.
You have worked with Fortune 500 companies and high-growth startups.
Your task is to produce a clear, actionable marketing campaign strategy.
Be specific, data-driven in your thinking, and commercially sharp.
Format your output in clean markdown with clear sections."""

    user_message = f"""Create a comprehensive marketing campaign strategy for this client:

**Business:** {brief['business_name']}
**Product/Service:** {brief['product_description']}
**Target Audience:** {brief['target_audience']}
**Campaign Goal:** {brief['campaign_goal']}
**Budget Range:** {brief.get('budget_range', 'Not specified')}
**Timeline:** {brief.get('timeline', '30 days')}
**Key Differentiators:** {brief.get('differentiators', 'Not specified')}

Produce a strategy covering:
1. **Positioning Statement** - How we position against competitors
2. **Core Message Architecture** - Primary message + 3 supporting pillars
3. **Target Audience Breakdown** - Primary, secondary segments with psychographic profiles
4. **Channel Strategy** - Top 4 channels with rationale and budget allocation %
5. **Campaign Phases** - Week-by-week execution timeline
6. **KPIs & Success Metrics** - What we measure and target benchmarks
7. **Risk Factors** - What could go wrong and mitigation plans

Be specific and actionable. No fluff."""

    message = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
    )

    return message.content[0].text
