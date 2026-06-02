#!/usr/bin/env python3
"""
Geotagged photo processor.

Reads GPS EXIF data, reverse geocodes to a location string, overlays the
location on the image, resizes to 1200px on the longest side, and saves the
result as a JPEG in a "processed/" subdirectory.

Usage:
    python process_photos.py [source_folder]

Install dependencies:
    pip install Pillow piexif geopy
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import piexif
from PIL import Image, ImageDraw, ImageFont
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".tiff", ".tif", ".png", ".webp", ".bmp"}
MAX_LONG_SIDE = 1200
GEOCODE_DELAY = 1.0  # seconds between Nominatim requests
TEXT_PADDING = 10
FONT_SIZE = 20
OVERLAY_ALPHA = 160  # 0-255 for the dark background box


def dms_to_decimal(dms, ref) -> float:
    """Convert degrees/minutes/seconds rational tuples to a decimal degree float."""
    degrees = dms[0][0] / dms[0][1]
    minutes = dms[1][0] / dms[1][1] / 60
    seconds = dms[2][0] / dms[2][1] / 3600
    value = degrees + minutes + seconds
    if ref in (b"S", b"W"):
        value = -value
    return value


def extract_gps(path: Path):
    """Return (lat, lon) from EXIF or None if GPS data is absent/unreadable."""
    try:
        exif = piexif.load(str(path))
    except Exception as exc:
        log.warning("%s: could not read EXIF — %s", path.name, exc)
        return None

    gps = exif.get("GPS", {})
    if not gps:
        return None

    try:
        lat = dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude],
                             gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude],
                             gps[piexif.GPSIFD.GPSLongitudeRef])
    except (KeyError, ZeroDivisionError, TypeError) as exc:
        log.warning("%s: malformed GPS data — %s", path.name, exc)
        return None

    return lat, lon


def reverse_geocode(geolocator, lat: float, lon: float) -> str:
    """Return a human-readable location string for the given coordinates."""
    try:
        location = geolocator.reverse((lat, lon), language="en", timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError) as exc:
        log.warning("Geocoding failed for (%.5f, %.5f): %s", lat, lon, exc)
        return f"{lat:.4f}, {lon:.4f}"

    if location is None:
        return f"{lat:.4f}, {lon:.4f}"

    addr = location.raw.get("address", {})
    parts = [
        addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
        addr.get("country"),
    ]
    return ", ".join(p for p in parts if p) or location.address


def resize_image(img: Image.Image) -> Image.Image:
    """Resize so the longest side equals MAX_LONG_SIDE, preserving aspect ratio."""
    w, h = img.size
    if max(w, h) <= MAX_LONG_SIDE:
        return img
    if w >= h:
        new_w, new_h = MAX_LONG_SIDE, int(h * MAX_LONG_SIDE / w)
    else:
        new_w, new_h = int(w * MAX_LONG_SIDE / h), MAX_LONG_SIDE
    return img.resize((new_w, new_h), Image.LANCZOS)


def load_font(size: int) -> ImageFont.ImageFont:
    """Try to load a truetype font; fall back to Pillow's built-in bitmap font."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def overlay_text(img: Image.Image, text: str) -> Image.Image:
    """Draw text in the bottom-right corner on a semi-transparent dark box."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(FONT_SIZE)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    iw, ih = img.size
    box_x1 = iw - text_w - TEXT_PADDING * 2
    box_y1 = ih - text_h - TEXT_PADDING * 2
    box_x2 = iw
    box_y2 = ih

    draw.rectangle([box_x1, box_y1, box_x2, box_y2],
                   fill=(0, 0, 0, OVERLAY_ALPHA))

    text_x = box_x1 + TEXT_PADDING
    text_y = box_y1 + TEXT_PADDING
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

    return Image.alpha_composite(img, overlay).convert("RGB")


def process_folder(source: Path) -> None:
    if not source.is_dir():
        log.error("'%s' is not a directory.", source)
        sys.exit(1)

    out_dir = source / "processed"
    out_dir.mkdir(exist_ok=True)

    photos = sorted(
        p for p in source.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not photos:
        log.info("No image files found in '%s'.", source)
        return

    geolocator = Nominatim(user_agent="geotagged-photo-processor/1.0")

    total = len(photos)
    for idx, photo in enumerate(photos, 1):
        print(f"[{idx}/{total}] {photo.name}", end=" ... ", flush=True)

        coords = extract_gps(photo)
        if coords is None:
            log.warning("%s: no GPS data, skipping.", photo.name)
            continue

        lat, lon = coords
        location_str = reverse_geocode(geolocator, lat, lon)
        time.sleep(GEOCODE_DELAY)

        try:
            img = Image.open(photo)
            # Apply EXIF orientation before any manipulation
            try:
                exif_bytes = piexif.load(str(photo))
                orientation = exif_bytes.get("0th", {}).get(piexif.ImageIFD.Orientation, 1)
                rotation_map = {3: 180, 6: 270, 8: 90}
                if orientation in rotation_map:
                    img = img.rotate(rotation_map[orientation], expand=True)
            except Exception:
                pass  # non-critical; proceed without rotation correction

            img = resize_image(img)
            img = overlay_text(img, location_str)
        except Exception as exc:
            log.error("%s: image processing failed — %s", photo.name, exc)
            continue

        out_path = out_dir / (photo.stem + ".jpg")
        img.save(out_path, "JPEG", quality=88, optimize=True)
        print(f"saved → processed/{out_path.name}  [{location_str}]")

    print(f"\nDone. Processed images are in '{out_dir}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process geotagged photos.")
    parser.add_argument(
        "source",
        nargs="?",
        default=".",
        help="Folder containing photos (default: current directory)",
    )
    args = parser.parse_args()
    process_folder(Path(args.source).resolve())


if __name__ == "__main__":
    main()
