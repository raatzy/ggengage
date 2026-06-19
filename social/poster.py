import json
import logging
from . import facebook, instagram, tiktok, twitter

logger = logging.getLogger(__name__)

HANDLERS = {
    "facebook": facebook.post,
    "instagram": instagram.post,
    "tiktok": tiktok.post,
    "x": twitter.post,
}


def post_to_platforms(
    text: str,
    hashtags: str,
    image_path: str | None,
    platforms: list[str],
) -> dict:
    """
    Post to each requested platform.
    Returns a dict mapping platform → result dict.
    """
    full_text = f"{text}\n\n{hashtags}".strip()
    results = {}

    for platform in platforms:
        handler = HANDLERS.get(platform.lower())
        if not handler:
            results[platform] = {"success": False, "error": "Unknown platform"}
            continue

        logger.info("Posting to %s…", platform)
        result = handler(full_text, image_path)
        results[platform] = result
        status = "OK" if result["success"] else f"FAILED — {result.get('error')}"
        logger.info("%s: %s", platform, status)

    return results


def results_to_json(results: dict) -> str:
    return json.dumps(results)


def results_from_json(raw: str) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}
