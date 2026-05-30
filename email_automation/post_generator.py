import anthropic
from .config import Config


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _client


def generate_social_post(subject: str, body: str) -> dict:
    """
    Ask Claude to turn an email into a social media post.

    Returns a dict with keys:
        headline   – short punchy opener line
        post_text  – full post body (without hashtags)
        hashtags   – space-separated hashtag string
    """
    prompt = f"""You are a social media manager for {Config.BUSINESS_NAME}, a web development \
agency that builds AI-powered websites using a Claude backend.

A client/partner sent the following email asking us to create a social media post:

SUBJECT: {subject}

BODY:
{body}

Create a social media post that:
1. Opens with an attention-grabbing HEADLINE (1 line, no hashtags).
2. Has 3–5 sentences of engaging body copy about the product/service/offer described in the email.
3. Ends with a call-to-action inviting people to sign up using the referral code \
{Config.REFERRAL_CODE} at {Config.BUSINESS_WEBSITE}.
4. Includes 8–12 relevant hashtags on a separate line — always include \
#WebGecko #WebDevelopment #AIWebsite.

Reply in this EXACT format (no extra text before or after):

HEADLINE: <your headline here>

POST:
<your post body here>

HASHTAGS: <hashtag1 hashtag2 ...>
"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    headline, post_text, hashtags = "", "", ""

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("HEADLINE:"):
            headline = line[len("HEADLINE:"):].strip()
        elif line.startswith("HASHTAGS:"):
            hashtags = line[len("HASHTAGS:"):].strip()

    # Extract the POST block
    if "POST:" in raw:
        post_block = raw.split("POST:", 1)[1]
        if "HASHTAGS:" in post_block:
            post_block = post_block.split("HASHTAGS:", 1)[0]
        post_text = post_block.strip()

    return {
        "headline": headline or "Exciting news from Web Gecko!",
        "post_text": post_text or raw,
        "hashtags": hashtags or "#WebGecko #WebDevelopment #AIWebsite",
    }
