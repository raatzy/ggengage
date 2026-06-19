import requests
import logging
import time
from email_automation.config import Config

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v19.0"


def post(text: str, image_path: str | None) -> dict:
    """
    Post to Instagram Business account.
    Instagram requires a publicly accessible image URL — we upload via
    the Facebook CDN first, then create the IG container.
    Returns {"success": bool, "id": str, "error": str}
    """
    if not Config.FACEBOOK_PAGE_TOKEN or not Config.INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Instagram credentials not configured"}

    if not image_path:
        return {"success": False, "error": "Instagram requires an image"}

    try:
        image_url = _get_public_url(image_path)
        if not image_url:
            return {"success": False, "error": "Could not get public image URL"}
        return _publish(text, image_url)
    except Exception as exc:
        logger.error("Instagram post failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _get_public_url(image_path: str) -> str | None:
    """Upload image to Facebook and get a temporary CDN URL via a page photo."""
    url = f"{GRAPH}/{Config.FACEBOOK_PAGE_ID}/photos"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            params={
                "access_token": Config.FACEBOOK_PAGE_TOKEN,
                "published": "false",
                "temporary": "true",
            },
            files={"source": f},
            timeout=60,
        )
    data = resp.json()
    if "id" not in data:
        logger.error("Instagram image upload error: %s", data)
        return None

    # Fetch the image URL from the uploaded photo object
    photo_resp = requests.get(
        f"{GRAPH}/{data['id']}",
        params={"fields": "images", "access_token": Config.FACEBOOK_PAGE_TOKEN},
        timeout=15,
    )
    images = photo_resp.json().get("images", [])
    if images:
        return images[0]["source"]
    return None


def _publish(caption: str, image_url: str) -> dict:
    token = Config.FACEBOOK_PAGE_TOKEN
    ig_id = Config.INSTAGRAM_ACCOUNT_ID

    # Step 1: create media container
    container_resp = requests.post(
        f"{GRAPH}/{ig_id}/media",
        params={"access_token": token},
        json={"image_url": image_url, "caption": caption},
        timeout=30,
    )
    container = container_resp.json()
    if "id" not in container:
        return {"success": False, "error": container.get("error", {}).get("message", str(container))}

    container_id = container["id"]

    # Step 2: poll until container is ready (usually instant)
    for _ in range(10):
        status_resp = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=10,
        )
        if status_resp.json().get("status_code") == "FINISHED":
            break
        time.sleep(2)

    # Step 3: publish
    publish_resp = requests.post(
        f"{GRAPH}/{ig_id}/media_publish",
        params={"access_token": token},
        json={"creation_id": container_id},
        timeout=30,
    )
    data = publish_resp.json()
    if "id" in data:
        return {"success": True, "id": data["id"]}
    return {"success": False, "error": data.get("error", {}).get("message", str(data))}
