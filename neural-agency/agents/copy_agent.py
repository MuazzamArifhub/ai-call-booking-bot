"""
Copy Agent - Produces high-converting ad copy, landing page copy, and headlines.
Thinks like a direct-response copywriter + brand storyteller hybrid.
"""

import anthropic


async def run_copy_agent(
    client: anthropic.AsyncAnthropic,
    brief: dict,
    strategy: str,
) -> str:
    """
    Generate ad copy, headlines, and landing page copy.
    Uses the strategy output to stay aligned with positioning.
    """
    system_prompt = """You are a world-class direct-response copywriter who has generated over $500M in revenue for clients.
You combine the conversion science of Claude Hopkins with the brand storytelling of David Ogilvy.
Every word you write earns its place. You write for humans first, algorithms second.
Format your output in clean, organized markdown."""

    user_message = f"""Write all copy assets for this campaign.

**Client:** {brief['business_name']}
**Product:** {brief['product_description']}
**Target Audience:** {brief['target_audience']}
**Campaign Goal:** {brief['campaign_goal']}
**Tone/Voice:** {brief.get('brand_voice', 'Professional but approachable')}

**Campaign Strategy Context:**
{strategy[:800]}

Produce ALL of the following copy assets:

## 1. HEADLINE BANK (10 headlines)
Write 10 headlines in different styles:
- 3 curiosity-driven
- 3 benefit-led
- 2 social proof / credibility
- 2 urgency / scarcity

## 2. FACEBOOK/INSTAGRAM ADS (3 complete ads)
Each ad should have: Hook (1 line), Body (3-4 lines), CTA (1 line)
Vary the angle: Problem-aware, Solution-aware, Product-aware

## 3. GOOGLE SEARCH ADS (3 ad groups)
Each: 3 headlines (30 chars max), 2 descriptions (90 chars max)

## 4. LANDING PAGE COPY
- Hero section: Headline + subheadline + CTA button text
- Value proposition section: 3 benefit blocks (icon name + headline + 2 sentences)
- Social proof section: 2 testimonial templates
- FAQ section: 5 most common objections + answers
- Final CTA section: Closing headline + CTA

## 5. EMAIL SUBJECT LINES (10 options)
Mix of curiosity, benefit, personalization, and re-engagement styles

Be sharp, specific, and conversion-focused. No generic copy."""

    message = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
    )

    return message.content[0].text
