import requests
import logging
from email_automation.config import Config

logger = logging.getLogger(__name__)

# TikTok Content Posting API
# Requires: TikTok for Business account + app approval
# Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
API_BASE = "https://open.tiktokapis.com/v2"


def post(text: str, image_path: str | None) -> dict:
    """
    Post a photo post to TikTok.
    NOTE: TikTok's Content Posting API requires app review from TikTok
    before it works in production. During development it only posts
    to your own account in sandbox mode.
    Returns {"success": bool, "id": str, "error": str}
    """
    if not Config.TIKTOK_ACCESS_TOKEN or not Config.TIKTOK_OPEN_ID:
        return {"success": False, "error": "TikTok credentials not configured"}

    if not image_path:
        return {"success": False, "error": "TikTok post requires an image"}

    try:
        return _post_photo(text, image_path)
    except Exception as exc:
        logger.error("TikTok post failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _post_photo(caption: str, image_path: str) -> dict:
    token = Config.TIKTOK_ACCESS_TOKEN
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # Step 1: initialise upload
    init_resp = requests.post(
        f"{API_BASE}/post/publish/content/init/",
        headers=headers,
        json={
            "post_info": {
                "title": caption[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "photo_cover_index": 0,
                "photo_images": [],  # filled after upload
            },
            "post_mode": "DIRECT_POST",
            "media_type": "PHOTO",
        },
        timeout=30,
    )
    init_data = init_resp.json().get("data", {})
    if "publish_id" not in init_data:
        err = init_resp.json().get("error", {}).get("message", str(init_resp.json()))
        return {"success": False, "error": f"TikTok init failed: {err}"}

    publish_id = init_data["publish_id"]
    upload_url = init_data.get("upload_url", "")

    # Step 2: upload image
    with open(image_path, "rb") as f:
        image_data = f.read()

    upload_resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(image_data)),
        },
        data=image_data,
        timeout=60,
    )
    if upload_resp.status_code not in (200, 204):
        return {"success": False, "error": f"TikTok image upload failed: {upload_resp.status_code}"}

    return {"success": True, "id": publish_id}
