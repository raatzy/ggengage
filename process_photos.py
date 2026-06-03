#!/usr/bin/env python3
"""
GG Engage Photo Processor — Windows GUI application.

Licensing model
---------------
• First 20 photos: free trial (counter persists through uninstall/reinstall)
• After 20 photos: $AUD 10 license required
• Activation: online (app calls the license server the first time a key is entered)
• Hardware binding: the server binds the key to this machine's fingerprint
  (motherboard serial + primary disk serial + CPU ID + Windows MachineGuid)
  on first activation; the same key cannot be activated on a different machine
• Subsequent startups: validated locally (works offline); server re-checked weekly

Install dependencies:
    pip install Pillow piexif geopy cryptography requests
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from urllib.parse import urlparse

import webbrowser

import requests
import piexif
from PIL import Image, ImageDraw, ImageFont
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes as _ch
except ImportError:
    sys.exit("Missing dependency — run:  pip install cryptography  then try again.")

_WIN = sys.platform == "win32"
if _WIN:
    import ctypes
    import ctypes.wintypes
    import winreg


# ── App constants ─────────────────────────────────────────────────────────────

APP_NAME          = "GG Engage Photo Processor"
APP_VERSION       = "1.0.0"
FREE_LIMIT        = 20
PRICE_AUD         = 10
SUPPORT_EMAIL     = "support@ggengage.com.au"
LICENSE_SERVER    = "https://api.ggengage.com.au"   # your Render.com URL
DEEP_LINK_SCHEME  = "ggphoto"
VALIDATE_INTERVAL = 7 * 24 * 3600                   # re-validate online weekly

# HMAC secret — must match LICENSE_HMAC_SECRET env var on the server
# and _LIC_SECRET / _SECRET in installer/keygen.py
_LIC_SECRET = b"GGEngagePhotoProc-k9xP2025#mR7"

# HKDF salt for local storage encryption
_KDF_SALT = b"GGEngPhotoProc-StoreSalt-2025#v1"

# ── Hidden local storage locations ───────────────────────────────────────────
# These survive app uninstall. See SoftwareSecurity skill for full rationale.

_APPDATA  = Path(os.environ.get("APPDATA",      str(Path.home())))
_LAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))

_REG_KEY = r"Software\Classes\AppID\{A3F7C2D1-4B8E-4F9A-9C0D-2E5B7A3F8C1D}"
_REG_VAL = "LocalService"

_FILE_A = (_APPDATA  / "Microsoft/Windows/Recent/AutomaticDestinations"
           / "a3f7c2d14b8e4f9a.automaticDestinations-ms")
_FILE_B = (_LAPPDATA / "Microsoft/Windows/Explorer"
           / "thumbcache_{A3F7C2D1-4B8E-4F9A-9C0D-2E5B7A3F8C1D}.db")

# ── Image constants ───────────────────────────────────────────────────────────

IMAGE_EXTS    = {".jpg", ".jpeg", ".tiff", ".tif", ".png", ".webp", ".bmp"}
MAX_LONG_SIDE = 1200
GEOCODE_DELAY = 1.0
TEXT_PADDING  = 10
FONT_SIZE     = 20
OVERLAY_ALPHA = 160

BG, FG, ACCENT = "#1e1e1e", "#f0f0f0", "#4caf50"


# ── Hardware fingerprinting ───────────────────────────────────────────────────

def _wmic(args: list[str]) -> str:
    """
    Run a wmic query with /value output and return the first non-empty value.
    Filters out OEM placeholder strings ("To Be Filled By O.E.M." etc.).
    """
    _oem_junk = {"to be filled by o.e.m.", "none", "n/a",
                 "default string", "not applicable", "", "0"}
    try:
        r = subprocess.run(
            ["wmic"] + args + ["/value"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000 if _WIN else 0)   # CREATE_NO_WINDOW
        for line in r.stdout.splitlines():
            if "=" in line:
                val = line.split("=", 1)[1].strip()
                if val.lower() not in _oem_junk:
                    return val
    except Exception:
        pass
    return ""


def _hardware_fingerprint() -> str:
    """
    Build a strong machine fingerprint from hardware identifiers.
    Used for online license binding — sent as a SHA-256 hash (not raw values).

    Sources (in priority order):
      1. Motherboard manufacturer + serial number
      2. Primary physical disk serial number
      3. CPU processor ID
      4. Windows MachineGuid (registry)
      5. C: volume serial (fastest fallback)
    """
    parts: list[str] = []

    if _WIN:
        # Motherboard
        mb_mfr    = _wmic(["baseboard", "get", "manufacturer"])
        mb_serial = _wmic(["baseboard", "get", "serialnumber"])
        if mb_serial:
            parts.append(f"mb:{mb_mfr}:{mb_serial}")

        # Primary disk (physical drive 0)
        disk = _wmic(["diskdrive", "where", "index=0", "get", "serialnumber"])
        if disk:
            parts.append(f"disk:{disk}")

        # CPU
        cpu = _wmic(["cpu", "get", "processorid"])
        if cpu:
            parts.append(f"cpu:{cpu}")

        # Windows MachineGuid
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            winreg.CloseKey(k)
            parts.append(f"guid:{guid}")
        except Exception:
            pass

        # C: volume serial (fastest; always available)
        try:
            serial = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.GetVolumeInformationW(
                "C:\\", None, 0, ctypes.byref(serial), None, None, None, 0)
            parts.append(f"vol:{serial.value:08x}")
        except Exception:
            pass

    parts.append(f"host:{os.environ.get('COMPUTERNAME', 'unknown')}")
    combined = "||".join(parts) or "no-hw-info"
    return hashlib.sha256(combined.encode()).hexdigest()


def _fast_machine_id() -> str:
    """
    Lighter fingerprint used only for local Fernet key derivation
    (no wmic calls — runs at import time without delaying startup).
    """
    parts: list[str] = []
    if _WIN:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            winreg.CloseKey(k)
            parts.append(f"guid:{guid}")
        except Exception:
            pass
        try:
            serial = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.GetVolumeInformationW(
                "C:\\", None, 0, ctypes.byref(serial), None, None, None, 0)
            parts.append(f"vol:{serial.value:08x}")
        except Exception:
            pass
    parts.append(f"host:{os.environ.get('COMPUTERNAME', 'unknown')}")
    return hashlib.sha256(("||".join(parts) or "no-hw").encode()).hexdigest()


# Derive and cache local Fernet key at import time (HKDF is instant)
_FERNET = Fernet(base64.urlsafe_b64encode(
    HKDF(algorithm=_ch.SHA256(), length=32,
         salt=_KDF_SALT,
         info=b"GGEngagePhotoProcessor-store-v1"
         ).derive(_fast_machine_id().encode())))


# ── Local storage (3 hidden locations) ───────────────────────────────────────

def _reg_read() -> bytes | None:
    if not _WIN:
        return None
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        data, _ = winreg.QueryValueEx(k, _REG_VAL)
        winreg.CloseKey(k)
        return bytes(data)
    except Exception:
        return None


def _reg_write(data: bytes) -> None:
    if not _WIN:
        return
    try:
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        winreg.SetValueEx(k, _REG_VAL, 0, winreg.REG_BINARY, data)
        winreg.CloseKey(k)
    except Exception:
        pass


def _file_read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except Exception:
        return None


def _file_write(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if _WIN:
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
            except Exception:
                pass
    except Exception:
        pass


def _decrypt_one(raw: bytes | None) -> dict | None:
    if raw is None:
        return None
    try:
        return json.loads(_FERNET.decrypt(raw).decode())
    except (InvalidToken, Exception):
        return None


def _load_config() -> dict:
    blobs   = [_reg_read(), _file_read(_FILE_A), _file_read(_FILE_B)]
    records = [_decrypt_one(b) for b in blobs]
    valid   = [r for r in records if r is not None]

    if not valid:
        return {"photos_processed": 0, "licensed": False,
                "license_key": None, "last_validated": 0}

    winner = max(valid, key=lambda c: (int(c.get("licensed", False)),
                                       c.get("photos_processed", 0)))

    encrypted = _FERNET.encrypt(json.dumps(winner).encode())
    if records[0] is None:
        _reg_write(encrypted)
    if records[1] is None:
        _file_write(_FILE_A, encrypted)
    if records[2] is None:
        _file_write(_FILE_B, encrypted)

    return winner


def _save_config(cfg: dict) -> None:
    encrypted = _FERNET.encrypt(json.dumps(cfg).encode())
    _reg_write(encrypted)
    _file_write(_FILE_A, encrypted)
    _file_write(_FILE_B, encrypted)


# ── License key HMAC (quick offline check) ────────────────────────────────────

def _validate_key_hmac(key: str) -> bool:
    k = key.strip().upper().replace("-", "").replace(" ", "")
    if len(k) != 16:
        return False
    payload  = k[:8]
    expected = hmac.new(_LIC_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    return hmac.compare_digest(k[8:], expected)


# ── Online activation ─────────────────────────────────────────────────────────

def _activate_online(key: str, fingerprint: str) -> tuple[bool, bool, str]:
    """
    POST to the license server.
    Returns (success, conflict, message).
    conflict=True means the key is valid but already bound to a different machine.
    """
    resp = requests.post(f"{LICENSE_SERVER}/api/activate",
                         json={"key": key, "fingerprint": fingerprint},
                         timeout=15)
    data = resp.json()
    return (data.get("success", False),
            data.get("conflict", False),
            data.get("message", "Unknown error"))


def _validate_online(key: str, fingerprint: str) -> bool:
    """Periodic background check. Returns False on any error (fail open)."""
    try:
        url  = f"{LICENSE_SERVER}/api/validate"
        resp = requests.get(url, params={"key": key, "fingerprint": fingerprint},
                            timeout=10)
        return resp.json().get("valid", False)
    except Exception:
        return True   # server unreachable → trust local cache


# ── Deep-link parser ──────────────────────────────────────────────────────────

def _extract_key_from_args(args: list[str]) -> str | None:
    """Extract license key from  ggphoto://activate/XXXX-XXXX-XXXX-XXXX  URL."""
    for arg in args:
        if arg.lower().startswith(f"{DEEP_LINK_SCHEME}://activate/"):
            return arg.split("/")[-1].strip()
    return None


# ── Image helpers ─────────────────────────────────────────────────────────────

def _dms_to_decimal(dms, ref) -> float:
    d = dms[0][0] / dms[0][1]
    m = dms[1][0] / dms[1][1] / 60
    s = dms[2][0] / dms[2][1] / 3600
    v = d + m + s
    if ref in (b"S", b"W"):
        v = -v
    return v


def _extract_gps(path: Path):
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
    addr    = loc.raw.get("address", {})
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
    for path in [f"{windir}/Fonts/arial.ttf",
                 f"{windir}/Fonts/segoeui.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
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
    coords = _extract_gps(photo)
    if coords is None:
        return None

    lat, lon = coords
    loc_str  = _geocode(geolocator, lat, lon)
    time.sleep(GEOCODE_DELAY)

    img = Image.open(photo)
    try:
        exif_data = piexif.load(str(photo))
        orient    = exif_data.get("0th", {}).get(piexif.ImageIFD.Orientation, 1)
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
    def __init__(self, pending_key: str | None = None):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("640x540")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.cfg = _load_config()
        self._hw_fingerprint: str | None = None   # computed lazily in bg thread
        self._build_ui()
        self._refresh_status()

        # Deep-link / auto-activation from email button
        if pending_key and not self.cfg["licensed"]:
            self.after(600, lambda: self._enter_license(prefill=pending_key))

        # Background: compute hw fingerprint + weekly online re-validation
        threading.Thread(target=self._background_init, daemon=True).start()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tk.Label(self, text=APP_NAME, font=("Segoe UI", 15, "bold"),
                 bg=BG, fg=ACCENT).pack(pady=(16, 2))
        tk.Label(self, text=f"Version {APP_VERSION}  ·  GG Engage",
                 font=("Segoe UI", 9), bg=BG, fg="#777").pack()

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

        self._status_var = tk.StringVar()
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=ACCENT).pack(pady=2)

        lf = tk.Frame(self, bg=BG)
        lf.pack(fill="both", expand=True, padx=14)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self._log = tk.Text(lf, height=14, bg="#252525", fg=FG,
                            font=("Consolas", 9), relief="flat",
                            yscrollcommand=sb.set, state="disabled")
        self._log.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log.yview)

        self._bar = ttk.Progressbar(self, mode="determinate")
        self._bar.pack(fill="x", padx=14, pady=4)

        bf = tk.Frame(self, bg=BG)
        bf.pack(pady=10)
        self._proc_btn = tk.Button(
            bf, text="Process Photos", width=18, command=self._start,
            cursor="hand2", bg=ACCENT, fg="white", relief="flat",
            font=("Segoe UI", 10, "bold"), activebackground="#388e3c")
        self._proc_btn.pack(side="left", padx=6)
        self._lic_btn = tk.Button(
            bf, text="Enter License Key", width=18,
            command=self._enter_license, cursor="hand2",
            bg="#3a3a3a", fg=FG, relief="flat",
            font=("Segoe UI", 10), activebackground="#555")
        self._lic_btn.pack(side="left", padx=6)

    # ── Helpers ──────────────────────────────────────────────────────────────

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

    def _background_init(self):
        """Run at startup in a daemon thread — does NOT block the UI."""
        # 1. Pre-compute hardware fingerprint so activation is instant
        self._hw_fingerprint = _hardware_fingerprint()

        # 2. Weekly online re-validation for licensed installs
        if not self.cfg.get("licensed"):
            return
        last = self.cfg.get("last_validated", 0)
        if time.time() - last < VALIDATE_INTERVAL:
            return
        key         = self.cfg.get("license_key", "")
        fingerprint = self._hw_fingerprint
        if key and fingerprint:
            still_valid = _validate_online(key, fingerprint)
            if not still_valid:
                # Server explicitly says revoked — disable locally
                self.cfg["licensed"]    = False
                self.cfg["license_key"] = None
                _save_config(self.cfg)
                self.after(0, self._refresh_status)
                self.after(0, lambda: messagebox.showwarning(
                    "License revoked",
                    "Your license has been revoked.\n"
                    f"Please contact {SUPPORT_EMAIL} for assistance."))
            else:
                self.cfg["last_validated"] = int(time.time())
                _save_config(self.cfg)

    # ── Processing ───────────────────────────────────────────────────────────

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

        if not self.cfg["licensed"]:
            remaining = FREE_LIMIT - self.cfg["photos_processed"]
            if remaining <= 0:
                self._prompt_purchase()
                return
            if len(photos) > remaining:
                if not messagebox.askyesno(
                    "Free trial limit",
                    f"Free trial: {remaining} photo(s) remaining.\n"
                    f"You selected {len(photos)} — only the first {remaining} "
                    f"will be processed.\n\n"
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

    # ── Licensing dialogs ─────────────────────────────────────────────────────

    def _prompt_purchase(self):
        messagebox.showinfo(
            "Free trial complete",
            f"You have used all {FREE_LIMIT} free photos.\n\n"
            f"To keep processing, please purchase a license for ${PRICE_AUD} AUD.\n\n"
            f"Visit:  ggengage.com.au\n\n"
            f"After payment your license key will be emailed to you automatically.")
        self._enter_license()

    def _enter_license(self, prefill: str = ""):
        key = simpledialog.askstring(
            "Enter License Key",
            "Enter your license key (format: XXXX-XXXX-XXXX-XXXX):",
            initialvalue=prefill,
            parent=self)
        if not key:
            return

        if not _validate_key_hmac(key):
            messagebox.showerror(
                "Invalid key",
                "That key format is not valid.\n"
                "Please check for typos and try again.\n\n"
                f"Contact {SUPPORT_EMAIL} if you need help.")
            return

        if self._hw_fingerprint is None:
            self._hw_fingerprint = _hardware_fingerprint()

        self._lic_btn.config(state="disabled", text="Activating…")
        self.update_idletasks()

        def _do_activate():
            try:
                ok, conflict, msg = _activate_online(key, self._hw_fingerprint)
            except requests.exceptions.ConnectionError:
                self.after(0, _restore_btn)
                self.after(0, messagebox.showerror, "Connection error",
                           "Could not connect to the activation server.\n"
                           "Please check your internet connection and try again.")
                return
            except Exception as exc:
                self.after(0, _restore_btn)
                self.after(0, messagebox.showerror, "Connection error", str(exc))
                return

            if ok:
                self.cfg.update(licensed=True,
                                license_key=key.strip().upper(),
                                last_validated=int(time.time()))
                _save_config(self.cfg)
                self.after(0, self._refresh_status)
                self.after(0, messagebox.showinfo, "License activated", msg)
            elif conflict:
                # Key is valid but bound to a different machine — show options
                self.after(0, _restore_btn)
                self.after(0, self._show_conflict_dialog, key)
            else:
                self.after(0, _restore_btn)
                self.after(0, messagebox.showerror, "Activation failed", msg)

        def _restore_btn():
            self._lic_btn.config(state="normal", text="Enter License Key")

        threading.Thread(target=_do_activate, daemon=True).start()

    # ── Machine-conflict resolution ───────────────────────────────────────────

    def _show_conflict_dialog(self, key: str):
        """Show the 3-option dialog when a key is already bound to another machine."""
        dlg = _DeviceConflictDialog(self)
        if dlg.result == _DeviceConflictDialog.NEW_MACHINE:
            self._flow_new_machine(key)
        elif dlg.result == _DeviceConflictDialog.NEW_PURCHASE:
            webbrowser.open(f"https://{SUPPORT_EMAIL.split('@')[1]}")
        elif dlg.result == _DeviceConflictDialog.COMPONENT:
            self._flow_component_replacement(key)

    def _flow_new_machine(self, key: str):
        """Step 1 — request a verification code; Step 2 — confirm it."""
        # Step 1: request code
        self._lic_btn.config(state="disabled", text="Sending code…")
        self.update_idletasks()

        def _request():
            try:
                resp = requests.post(f"{LICENSE_SERVER}/api/transfer/request",
                                     json={"key": key}, timeout=15)
                data = resp.json()
            except Exception as exc:
                self.after(0, _restore)
                self.after(0, messagebox.showerror, "Connection error", str(exc))
                return

            if not data.get("success"):
                self.after(0, _restore)
                self.after(0, messagebox.showerror, "Transfer failed",
                           data.get("message", "Unknown error"))
                return

            self.after(0, _restore)
            self.after(0, _ask_code, data.get("message", ""))

        def _ask_code(server_msg: str):
            code = simpledialog.askstring(
                "Verification Code",
                f"{server_msg}\n\nEnter the 6-digit code from your email:",
                parent=self)
            if not code:
                return

            self._lic_btn.config(state="disabled", text="Verifying…")
            self.update_idletasks()
            threading.Thread(target=_confirm, args=(code,), daemon=True).start()

        def _confirm(code: str):
            try:
                resp = requests.post(f"{LICENSE_SERVER}/api/transfer/confirm",
                                     json={"key": key, "code": code.strip(),
                                           "fingerprint": self._hw_fingerprint},
                                     timeout=15)
                data = resp.json()
            except Exception as exc:
                self.after(0, _restore)
                self.after(0, messagebox.showerror, "Connection error", str(exc))
                return

            self.after(0, _restore)
            if data.get("success"):
                self.cfg.update(licensed=True,
                                license_key=key.strip().upper(),
                                last_validated=int(time.time()))
                _save_config(self.cfg)
                self.after(0, self._refresh_status)
                self.after(0, messagebox.showinfo,
                           "License transferred", data["message"])
            else:
                self.after(0, messagebox.showerror,
                           "Transfer failed", data.get("message", "Unknown error"))

        def _restore():
            self._lic_btn.config(state="normal", text="Enter License Key")

        threading.Thread(target=_request, daemon=True).start()

    def _flow_component_replacement(self, key: str):
        """Log a support ticket and open the email client for manual processing."""
        dlg = _ComponentDetailDialog(self)
        if dlg.component is None:
            return

        def _log_ticket():
            try:
                resp = requests.post(
                    f"{LICENSE_SERVER}/api/support/ticket",
                    json={"key": key,
                          "ticket_type": "component_replacement",
                          "component":   dlg.component,
                          "description": dlg.description},
                    timeout=15)
                data = resp.json()
            except Exception:
                data = {"success": False, "ticket_ref": "N/A",
                        "message": "Could not log ticket — please email us directly."}

            ticket_ref = data.get("ticket_ref", "")
            self.after(0, _open_email_and_notify, ticket_ref,
                       data.get("message", ""))

        def _open_email_and_notify(ticket_ref: str, server_msg: str):
            subj = (f"License Transfer Request — {ticket_ref}"
                    if ticket_ref else "License Transfer Request")
            body = (f"License Key: {key}\n"
                    f"Ticket Reference: {ticket_ref}\n"
                    f"Component Replaced: {dlg.component}\n\n"
                    f"Details:\n{dlg.description}\n\n"
                    f"Please transfer my license to my current computer.")
            import urllib.parse
            mailto = (f"mailto:{SUPPORT_EMAIL}"
                      f"?subject={urllib.parse.quote(subj)}"
                      f"&body={urllib.parse.quote(body)}")
            webbrowser.open(mailto)
            messagebox.showinfo("Support Request Logged", server_msg)

        threading.Thread(target=_log_ticket, daemon=True).start()


# ── Device-conflict resolution dialog ────────────────────────────────────────

class _DeviceConflictDialog(tk.Toplevel):
    """
    Shown when activation is rejected due to a hardware fingerprint mismatch.
    Presents three clearly labelled paths so the customer can self-serve.
    """
    NEW_MACHINE  = "new_machine"
    NEW_PURCHASE = "new_purchase"
    COMPONENT    = "component"

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.result: str | None = None
        self.title("License Already Activated")
        self.geometry("500x410")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._build()
        self.wait_window()

    def _build(self):
        tk.Label(self,
                 text="This license key is already activated\non a different device.",
                 font=("Segoe UI", 12, "bold"), bg=BG, fg=FG,
                 justify="center").pack(pady=(22, 4))
        tk.Label(self,
                 text="What best describes your situation?",
                 font=("Segoe UI", 10), bg=BG, fg="#999").pack(pady=(0, 14))

        options = [
            (self.NEW_MACHINE,
             "I purchased a new computer",
             "Deactivate the old machine and activate this one.\n"
             "A 6-digit code will be emailed to your registered address."),
            (self.NEW_PURCHASE,
             "I want to purchase a new license",
             f"Open the purchase page in your browser (${PRICE_AUD} AUD)."),
            (self.COMPONENT,
             "I replaced a component  (hard drive / motherboard)",
             "The hardware change altered this device's fingerprint.\n"
             "Log a support request — we will transfer your license manually\n"
             "within 1 business day."),
        ]
        for choice, title, desc in options:
            self._make_option(choice, title, desc)

        tk.Button(self, text="Cancel", command=self.destroy,
                  bg="#3a3a3a", fg=FG, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2").pack(pady=(6, 18))

    def _make_option(self, choice: str, title: str, desc: str):
        frame = tk.Frame(self, bg="#2b2b2b", cursor="hand2")
        frame.pack(fill="x", padx=18, pady=5)
        tk.Label(frame, text=title, font=("Segoe UI", 10, "bold"),
                 bg="#2b2b2b", fg=ACCENT, anchor="w",
                 cursor="hand2").pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(frame, text=desc, font=("Segoe UI", 9),
                 bg="#2b2b2b", fg="#aaa", anchor="w", justify="left",
                 cursor="hand2").pack(fill="x", padx=14, pady=(0, 10))

        def _hover_on(e,  f=frame): _set_bg(f, "#3a3a3a")
        def _hover_off(e, f=frame): _set_bg(f, "#2b2b2b")
        def _click(e, c=choice): self._choose(c)

        for w in [frame] + list(frame.winfo_children()):
            w.bind("<Enter>",    _hover_on)
            w.bind("<Leave>",    _hover_off)
            w.bind("<Button-1>", _click)

    def _choose(self, choice: str):
        self.result = choice
        self.destroy()


def _set_bg(widget: tk.Widget, color: str):
    widget.configure(bg=color)
    for child in widget.winfo_children():
        child.configure(bg=color)


# ── Component detail dialog ───────────────────────────────────────────────────

class _ComponentDetailDialog(tk.Toplevel):
    """
    Collects component type and description for a manual transfer request.
    """
    _COMPONENTS = [
        "Hard Drive / SSD",
        "Motherboard",
        "Hard Drive + Motherboard",
        "Other component",
    ]

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.component:   str | None = None
        self.description: str        = ""
        self.title("Component Replacement Details")
        self.geometry("420x300")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._build()
        self.wait_window()

    def _build(self):
        tk.Label(self, text="What did you replace?",
                 font=("Segoe UI", 11, "bold"), bg=BG, fg=FG).pack(pady=(18, 8))

        self._comp_var = tk.StringVar(value=self._COMPONENTS[0])
        for comp in self._COMPONENTS:
            tk.Radiobutton(self, text=comp, variable=self._comp_var, value=comp,
                           bg=BG, fg=FG, selectcolor="#3a3a3a",
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 10)).pack(anchor="w", padx=30)

        tk.Label(self, text="Briefly describe what happened (optional):",
                 font=("Segoe UI", 9), bg=BG, fg="#999").pack(anchor="w",
                                                               padx=30, pady=(12, 4))
        self._desc = tk.Text(self, height=3, bg="#2b2b2b", fg=FG,
                             insertbackground=FG, relief="flat",
                             font=("Segoe UI", 9))
        self._desc.pack(fill="x", padx=30)

        bf = tk.Frame(self, bg=BG)
        bf.pack(pady=14)
        tk.Button(bf, text="Submit Request", command=self._submit,
                  bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground="#388e3c").pack(side="left", padx=6)
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg="#3a3a3a", fg=FG, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2").pack(side="left")

    def _submit(self):
        self.component   = self._comp_var.get()
        self.description = self._desc.get("1.0", "end").strip()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    pending_key = _extract_key_from_args(sys.argv[1:])
    app = App(pending_key=pending_key)
    app.mainloop()


if __name__ == "__main__":
    main()
