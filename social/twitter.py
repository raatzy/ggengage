import tweepy
import logging
from email_automation.config import Config

logger = logging.getLogger(__name__)


def _get_client():
    return tweepy.Client(
        consumer_key=Config.TWITTER_API_KEY,
        consumer_secret=Config.TWITTER_API_SECRET,
        access_token=Config.TWITTER_ACCESS_TOKEN,
        access_token_secret=Config.TWITTER_ACCESS_TOKEN_SECRET,
    )


def _get_api_v1():
    """API v1.1 client needed for media uploads."""
    auth = tweepy.OAuth1UserHandler(
        Config.TWITTER_API_KEY,
        Config.TWITTER_API_SECRET,
        Config.TWITTER_ACCESS_TOKEN,
        Config.TWITTER_ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth)


def post(text: str, image_path: str | None) -> dict:
    """
    Post to X (Twitter).
    NOTE: Requires X Basic plan ($100/mo) for write access.
    Returns {"success": bool, "id": str, "error": str}
    """
    if not all([
        Config.TWITTER_API_KEY, Config.TWITTER_API_SECRET,
        Config.TWITTER_ACCESS_TOKEN, Config.TWITTER_ACCESS_TOKEN_SECRET,
    ]):
        return {"success": False, "error": "X (Twitter) credentials not configured"}

    # X has a 280 character limit — truncate gracefully
    tweet_text = text[:277] + "…" if len(text) > 280 else text

    try:
        client = _get_client()
        media_id = None

        if image_path:
            api_v1 = _get_api_v1()
            media = api_v1.media_upload(filename=image_path)
            media_id = media.media_id

        response = client.create_tweet(
            text=tweet_text,
            media_ids=[media_id] if media_id else None,
        )
        tweet_id = response.data["id"]
        return {"success": True, "id": tweet_id}

    except tweepy.TweepyException as exc:
        logger.error("X post failed: %s", exc)
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.error("X post unexpected error: %s", exc)
        return {"success": False, "error": str(exc)}
