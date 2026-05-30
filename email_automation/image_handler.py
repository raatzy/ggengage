import os
import uuid
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .config import Config


def save_image_from_bytes(data: bytes, ext: str = "jpg") -> str:
    """Save raw image bytes to the uploads folder, return relative path."""
    os.makedirs(Config.UPLOADS_PATH, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(Config.UPLOADS_PATH, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


def create_branded_image(headline: str, body_text: str = "") -> str:
    """
    Generate a 1080×1080 branded Web Gecko social card when no image
    is attached to the email.
    """
    W, H = 1080, 1080

    # Brand colours: deep forest green → teal gradient feel
    bg_top = (15, 82, 55)
    bg_bot = (10, 40, 30)
    accent = (0, 200, 140)
    white = (255, 255, 255)
    light_grey = (200, 220, 210)

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Background gradient (simple vertical)
    for y in range(H):
        t = y / H
        r = int(bg_top[0] + t * (bg_bot[0] - bg_top[0]))
        g = int(bg_top[1] + t * (bg_bot[1] - bg_top[1]))
        b = int(bg_top[2] + t * (bg_bot[2] - bg_top[2]))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Accent bar at top
    draw.rectangle([0, 0, W, 8], fill=accent)

    # Logo area — ASCII gecko text mark
    gecko_art = [
        "  /\\_/\\  ",
        " ( o.o ) ",
        "  > ^ <  ",
    ]

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 58)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 32)
    except OSError:
        font_large = font_medium = font_small = font_mono = ImageFont.load_default()

    # Gecko ASCII art
    y_offset = 80
    for line in gecko_art:
        bbox = draw.textbbox((0, 0), line, font=font_mono)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y_offset), line, font=font_mono, fill=accent)
        y_offset += 40

    # Business name
    y_offset += 20
    bname = Config.BUSINESS_NAME.upper()
    bbox = draw.textbbox((0, 0), bname, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y_offset), bname, font=font_large, fill=white)
    y_offset += 80

    # Divider
    draw.rectangle([120, y_offset, W - 120, y_offset + 3], fill=accent)
    y_offset += 30

    # Headline — word-wrap at ~28 chars per line
    headline = headline.strip()
    words = headline.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) > 28:
            if current:
                lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    for line in lines[:4]:
        bbox = draw.textbbox((0, 0), line, font=font_large)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y_offset), line, font=font_large, fill=white)
        y_offset += 68

    y_offset += 20

    # Body text snippet
    if body_text:
        snippet = body_text[:120].strip()
        if len(body_text) > 120:
            snippet += "…"
        bwords = snippet.split()
        blines, cur = [], ""
        for w in bwords:
            test = f"{cur} {w}".strip()
            if len(test) > 38:
                if cur:
                    blines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            blines.append(cur)
        for line in blines[:4]:
            bbox = draw.textbbox((0, 0), line, font=font_medium)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y_offset), line, font=font_medium, fill=light_grey)
            y_offset += 48

    # Bottom referral block
    footer_y = H - 160
    draw.rectangle([0, footer_y, W, H], fill=(0, 0, 0, 180))
    ref_text = f"Use code  {Config.REFERRAL_CODE}  to get started"
    bbox = draw.textbbox((0, 0), ref_text, font=font_medium)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, footer_y + 20), ref_text, font=font_medium, fill=accent)

    url_text = Config.BUSINESS_WEBSITE
    bbox = draw.textbbox((0, 0), url_text, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, footer_y + 72), url_text, font=font_small, fill=white)

    # Accent bar at bottom
    draw.rectangle([0, H - 8, W, H], fill=accent)

    os.makedirs(Config.UPLOADS_PATH, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    path = os.path.join(Config.UPLOADS_PATH, filename)
    img.save(path, "PNG")
    return path
