"""
Content Agent - Produces a full social media content calendar and email sequence.
Thinks like a seasoned content strategist and community builder.
"""

import anthropic


async def run_content_agent(
    client: anthropic.AsyncAnthropic,
    brief: dict,
    strategy: str,
) -> str:
    """
    Generate a 30-day social content calendar and 5-email welcome sequence.
    """
    system_prompt = """You are a top-tier content strategist who has grown brands from 0 to 1M followers.
You understand the algorithm, but more importantly you understand people.
You create content that drives real engagement, builds community, and converts followers into customers.
Format your output in clean, organized markdown with specific, ready-to-post content."""

    user_message = f"""Create a complete content plan for this brand.

**Client:** {brief['business_name']}
**Product:** {brief['product_description']}
**Target Audience:** {brief['target_audience']}
**Campaign Goal:** {brief['campaign_goal']}
**Tone/Voice:** {brief.get('brand_voice', 'Professional but approachable')}

**Strategy Context:**
{strategy[:600]}

Produce the following:

## 1. SOCIAL MEDIA CONTENT CALENDAR (30 days)

For each week, provide 5 posts (Mon-Fri) with:
- Platform (LinkedIn/Instagram/Twitter/X)
- Post type (Educational/Behind-scenes/Social proof/Promotional/Engagement)
- Full post copy (ready to publish)
- Hashtag set (for Instagram posts)

Format each post as:
**Day X | [Platform] | [Type]**
[Full copy]
[Hashtags if applicable]

## 2. EMAIL WELCOME SEQUENCE (5 emails)

For each email:
**Email [N]: [Name]** (sent Day X after signup)
- Subject line:
- Preview text:
- Opening line:
- Body (3-4 paragraphs):
- CTA:

Emails should follow this arc:
1. Welcome + instant value delivery
2. Origin story / why we exist
3. Customer transformation story
4. Objection handling + social proof
5. Soft pitch + urgency

Make every piece of content specific to this brand. No generic templates."""

    message = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
    )

    return message.content[0].text


async def run_seo_agent(
    client: anthropic.AsyncAnthropic,
    brief: dict,
    strategy: str,
) -> str:
    """
    Generate SEO content brief and blog post outline.
    """
    system_prompt = """You are an SEO strategist and content director who has ranked hundreds of pages #1 on Google.
You understand both technical SEO and the art of creating content that people actually want to read and share.
You think in terms of search intent, topical authority, and conversion paths."""

    user_message = f"""Create an SEO content strategy and blog outline for this brand.

**Client:** {brief['business_name']}
**Product:** {brief['product_description']}
**Target Audience:** {brief['target_audience']}
**Campaign Goal:** {brief['campaign_goal']}

Produce:

## 1. KEYWORD STRATEGY
- 5 primary commercial keywords (with estimated intent and competition level)
- 10 long-tail blog keywords
- 5 competitor gap keywords

## 2. CONTENT CLUSTER MAP
- 1 pillar page topic
- 5 cluster page topics that support it
- Internal linking strategy

## 3. FLAGSHIP BLOG POST
Write a complete, publish-ready blog post:
- SEO-optimized title
- Meta description (155 chars)
- Full article (800-1000 words) with H2/H3 structure
- Include: hook, problem, solution, proof, CTA

Make it genuinely useful and specific to this niche."""

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
    )

    return message.content[0].text
