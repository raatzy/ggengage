#!/usr/bin/env python3
"""
GG Engage Photo Processor — Windows GUI application.
Reads GPS EXIF data, reverse geocodes to city/country, overlays the location
on each photo, resizes to 1200 px on the longest side, and saves the result
as a JPEG in a 'processed/' subfolder. Free for the first 20 photos;
a license key is required for unlimited use.

Install dependencies:
    pip install Pillow piexif geopy
"""

import hashlib
import hmac
import json
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

import piexif
from PIL import Image, ImageDraw, ImageFont
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# ── App constants ─────────────────────────────────────────────────────────────

APP_NAME    = "GG Engage Photo Processor"
APP_VERSION = "1.0.0"
FREE_LIMIT  = 20
PRICE_AUD   = 10
SUPPORT_EMAIL = "support@ggengage.com.au"

# License validation key (baked into the exe — keep this private)
_LICENSE_SECRET = b"GGEngagePhotoProc-k9xP2025#mR7"

# Per-user config stored in %APPDATA%\GGEngagePhotoProcessor\
CONFIG_DIR  = Path(os.environ.get("APPDATA", str(Path.home()))) / "GGEngagePhotoProcessor"
CONFIG_FILE = CONFIG_DIR / "config.json"

IMAGE_EXTS    = {".jpg", ".jpeg", ".tiff", ".tif", ".png", ".webp", ".bmp"}
MAX_LONG_SIDE = 1200
GEOCODE_DELAY = 1.0     # seconds — respects Nominatim's usage policy
TEXT_PADDING  = 10
FONT_SIZE     = 20
OVERLAY_ALPHA = 160     # 0-255 darkness of the location label background

BG, FG, ACCENT = "#1e1e1e", "#f0f0f0", "#4caf50"


# ── License helpers ───────────────────────────────────────────────────────────

def _validate_key(key: str) -> bool:
    """
    Offline validation. Key format: XXXX-XXXX-XXXX-XXXX (16 hex chars).
    First 8 chars are the payload; last 8 are HMAC-SHA256(SECRET, payload)[:8].
    """
    k = key.strip().upper().replace("-", "").replace(" ", "")
    if len(k) != 16:
        return False
    payload = k[:8]
    expected = hmac.new(_LICENSE_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    return k[8:] == expected


def _load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"photos_processed": 0, "licensed": False, "license_key": None}


def _save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── Image processing ──────────────────────────────────────────────────────────

def _dms_to_decimal(dms, ref) -> float:
    d = dms[0][0] / dms[0][1]
    m = dms[1][0] / dms[1][1] / 60
    s = dms[2][0] / dms[2][1] / 3600
    v = d + m + s
    if ref in (b"S", b"W"):
        v = -v
    return v


def _extract_gps(path: Path):
    """Return (lat, lon) from EXIF, or None if absent/unreadable."""
    try:
        exif = piexif.load(str(path))
    except Exception:
        return None
    gps = exif.get("GPS", {})
    if not gps:
        return None
    try:
        lat = _dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude],
                              gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = _dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude],
                              gps[piexif.GPSIFD.GPSLongitudeRef])
    except (KeyError, ZeroDivisionError, TypeError):
        return None
    return lat, lon


def _geocode(geolocator, lat: float, lon: float) -> str:
    try:
        loc = geolocator.reverse((lat, lon), language="en", timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError):
        return f"{lat:.4f}, {lon:.4f}"
    if loc is None:
        return f"{lat:.4f}, {lon:.4f}"
    addr = loc.raw.get("address", {})
    city    = (addr.get("city") or addr.get("town")
               or addr.get("village") or addr.get("county"))
    country = addr.get("country")
    parts   = [p for p in (city, country) if p]
    return ", ".join(parts) if parts else loc.address


def _resize(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) <= MAX_LONG_SIDE:
        return img
    scale = MAX_LONG_SIDE / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _load_font(size: int) -> ImageFont.ImageFont:
    windir = os.environ.get("WINDIR", "C:/Windows")
    for path in [
        f"{windir}/Fonts/arial.ttf",
        f"{windir}/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


def _overlay(img: Image.Image, text: str) -> Image.Image:
    img   = img.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw  = ImageDraw.Draw(layer)
    font  = _load_font(FONT_SIZE)
    bbox  = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    iw, ih = img.size
    x1 = iw - tw - TEXT_PADDING * 2
    y1 = ih - th - TEXT_PADDING * 2
    draw.rectangle([x1, y1, iw, ih], fill=(0, 0, 0, OVERLAY_ALPHA))
    draw.text((x1 + TEXT_PADDING, y1 + TEXT_PADDING),
              text, font=font, fill=(255, 255, 255, 255))
    return Image.alpha_composite(img, layer).convert("RGB")


def _process_photo(photo: Path, geolocator) -> str | None:
    """
    Process one photo. Returns the location string on success,
    or None if the photo has no GPS data (caller should skip it).
    """
    coords = _extract_gps(photo)
    if coords is None:
        return None

    lat, lon = coords
    loc_str  = _geocode(geolocator, lat, lon)
    time.sleep(GEOCODE_DELAY)

    img = Image.open(photo)

    # Correct EXIF orientation before resizing
    try:
        exif_data = piexif.load(str(photo))
        orient = exif_data.get("0th", {}).get(piexif.ImageIFD.Orientation, 1)
        for tag, deg in {3: 180, 6: 270, 8: 90}.items():
            if orient == tag:
                img = img.rotate(deg, expand=True)
                break
    except Exception:
        pass

    img = _resize(img)
    img = _overlay(img, loc_str)

    out_dir = photo.parent / "processed"
    out_dir.mkdir(exist_ok=True)
    img.save(out_dir / (photo.stem + ".jpg"), "JPEG", quality=88, optimize=True)
    return loc_str


# ── Main window ───────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("640x540")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.cfg = _load_config()
        self._build_ui()
        self._refresh_status()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        tk.Label(self, text=APP_NAME, font=("Segoe UI", 15, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(16, 2))
        tk.Label(self, text=f"Version {APP_VERSION}  ·  GG Engage",
                 font=("Segoe UI", 9), bg=BG, fg="#777").pack()

        # Folder row
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=14, pady=8)
        tk.Label(row, text="Photo folder:", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self._folder = tk.StringVar(value=str(Path.home() / "Pictures"))
        tk.Entry(row, textvariable=self._folder, width=44,
                 bg="#2b2b2b", fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 9)).pack(side="left", padx=6)
        tk.Button(row, text="Browse…", command=self._browse,
                  bg="#3a3a3a", fg=FG, relief="flat",
                  activebackground=ACCENT, cursor="hand2").pack(side="left")

        # Status line
        self._status_var = tk.StringVar()
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=ACCENT).pack(pady=2)

        # Log box
        lf = tk.Frame(self, bg=BG)
        lf.pack(fill="both", expand=True, padx=14)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self._log = tk.Text(lf, height=14, bg="#252525", fg=FG,
                            font=("Consolas", 9), relief="flat",
                            yscrollcommand=sb.set, state="disabled")
        self._log.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log.yview)

        # Progress bar
        self._bar = ttk.Progressbar(self, mode="determinate")
        self._bar.pack(fill="x", padx=14, pady=4)

        # Action buttons
        bf = tk.Frame(self, bg=BG)
        bf.pack(pady=10)
        self._proc_btn = tk.Button(
            bf, text="Process Photos", width=18,
            command=self._start, cursor="hand2",
            bg=ACCENT, fg="white", relief="flat",
            font=("Segoe UI", 10, "bold"), activebackground="#388e3c")
        self._proc_btn.pack(side="left", padx=6)
        self._lic_btn = tk.Button(
            bf, text="Enter License Key", width=18,
            command=self._enter_license, cursor="hand2",
            bg="#3a3a3a", fg=FG, relief="flat",
            font=("Segoe UI", 10), activebackground="#555")
        self._lic_btn.pack(side="left", padx=6)

    # ── Event handlers ───────────────────────────────────────────────────────

    def _browse(self):
        d = filedialog.askdirectory(title="Select photo folder")
        if d:
            self._folder.set(d)

    def _write_log(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _refresh_status(self):
        if self.cfg["licensed"]:
            self._status_var.set("Status: LICENSED — unlimited photos")
            self._lic_btn.config(text="Licensed", state="disabled", bg="#2e7d32")
        else:
            left = max(0, FREE_LIMIT - self.cfg["photos_processed"])
            self._status_var.set(
                f"Status: FREE TRIAL — {left} of {FREE_LIMIT} free photos remaining"
                f"  (${PRICE_AUD} AUD to unlock)")

    def _start(self):
        folder = Path(self._folder.get())
        if not folder.is_dir():
            messagebox.showerror("Error", f"Folder not found:\n{folder}")
            return

        photos = sorted(p for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
        if not photos:
            messagebox.showinfo("No images",
                                "No image files found in that folder.")
            return

        # Enforce trial limit
        if not self.cfg["licensed"]:
            remaining = FREE_LIMIT - self.cfg["photos_processed"]
            if remaining <= 0:
                self._prompt_purchase()
                return
            if len(photos) > remaining:
                if not messagebox.askyesno(
                    "Free trial limit",
                    f"Your free trial allows {remaining} more photo(s), "
                    f"but you selected {len(photos)}.\n\n"
                    f"Only the first {remaining} will be processed.\n\n"
                    f"Purchase a license (${PRICE_AUD} AUD) for unlimited use.\n\n"
                    f"Continue with {remaining} photo(s)?"):
                    return
                photos = photos[:remaining]

        self._proc_btn.config(state="disabled")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._bar["value"]   = 0
        self._bar["maximum"] = len(photos)

        threading.Thread(target=self._worker, args=(photos,), daemon=True).start()

    def _worker(self, photos):
        geo  = Nominatim(user_agent="gg-engage-photo-processor/1.0")
        done = 0
        for i, photo in enumerate(photos, 1):
            self.after(0, self._write_log, f"[{i}/{len(photos)}] {photo.name}")
            try:
                loc = _process_photo(photo, geo)
                if loc is None:
                    self.after(0, self._write_log,
                               "  Warning: no GPS data — skipped")
                else:
                    self.after(0, self._write_log, f"  Saved  ->  {loc}")
                    done += 1
                    self.cfg["photos_processed"] += 1
                    _save_config(self.cfg)
            except Exception as exc:
                self.after(0, self._write_log, f"  Error: {exc}")
            self.after(0, self._tick, i)
        self.after(0, self._finished, done, len(photos))

    def _tick(self, n: int):
        self._bar["value"] = n
        self._refresh_status()

    def _finished(self, done: int, total: int):
        self._proc_btn.config(state="normal")
        self._refresh_status()
        out = Path(self._folder.get()) / "processed"
        self._write_log(f"\nFinished: {done}/{total} photos saved to:\n{out}")
        if not self.cfg["licensed"] and \
                self.cfg["photos_processed"] >= FREE_LIMIT:
            self._prompt_purchase()

    def _prompt_purchase(self):
        messagebox.showinfo(
            "Free trial complete",
            f"You have used all {FREE_LIMIT} free photos.\n\n"
            f"To keep processing, please purchase a license for ${PRICE_AUD} AUD.\n\n"
            f"Contact:  {SUPPORT_EMAIL}\n\n"
            f"After payment you will receive a 16-character license key.")
        self._enter_license()

    def _enter_license(self):
        key = simpledialog.askstring(
            "Enter License Key",
            "Enter your license key (format: XXXX-XXXX-XXXX-XXXX):",
            parent=self)
        if not key:
            return
        if _validate_key(key):
            self.cfg.update(licensed=True,
                            license_key=key.strip().upper())
            _save_config(self.cfg)
            self._refresh_status()
            messagebox.showinfo(
                "License activated",
                "Your license has been activated — thank you for your purchase!\n\n"
                "You can now process unlimited photos.")
        else:
            messagebox.showerror(
                "Invalid key",
                "That license key was not recognised.\n"
                "Please check for typos and try again.\n\n"
                f"If the problem continues, contact {SUPPORT_EMAIL}")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
