import requests
import logging
from email_automation.config import Config

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v19.0"


def post(text: str, image_path: str | None) -> dict:
    """
    Post to Facebook Page with an optional image.
    Returns {"success": bool, "id": str, "error": str}
    """
    if not Config.FACEBOOK_PAGE_TOKEN or not Config.FACEBOOK_PAGE_ID:
        return {"success": False, "error": "Facebook credentials not configured"}

    try:
        if image_path:
            photo_id = _upload_photo(image_path)
            if not photo_id:
                return {"success": False, "error": "Photo upload failed"}
            result = _post_with_photo(text, photo_id)
        else:
            result = _post_text(text)
        return result
    except Exception as exc:
        logger.error("Facebook post failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _upload_photo(image_path: str) -> str | None:
    url = f"{GRAPH}/{Config.FACEBOOK_PAGE_ID}/photos"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            params={"access_token": Config.FACEBOOK_PAGE_TOKEN, "published": "false"},
            files={"source": f},
            timeout=60,
        )
    data = resp.json()
    if "id" in data:
        return data["id"]
    logger.error("Facebook photo upload error: %s", data)
    return None


def _post_with_photo(text: str, photo_id: str) -> dict:
    url = f"{GRAPH}/{Config.FACEBOOK_PAGE_ID}/feed"
    resp = requests.post(
        url,
        params={"access_token": Config.FACEBOOK_PAGE_TOKEN},
        json={"message": text, "attached_media": [{"media_fbid": photo_id}]},
        timeout=30,
    )
    data = resp.json()
    if "id" in data:
        return {"success": True, "id": data["id"]}
    return {"success": False, "error": data.get("error", {}).get("message", str(data))}


def _post_text(text: str) -> dict:
    url = f"{GRAPH}/{Config.FACEBOOK_PAGE_ID}/feed"
    resp = requests.post(
        url,
        params={"access_token": Config.FACEBOOK_PAGE_TOKEN},
        json={"message": text},
        timeout=30,
    )
    data = resp.json()
    if "id" in data:
        return {"success": True, "id": data["id"]}
    return {"success": False, "error": data.get("error", {}).get("message", str(data))}
