# SoftwareSecurity

Implement a robust, machine-bound, multi-location software protection system for a Windows Python desktop application. This system provides:

- **Free trial enforcement** that survives uninstall/reinstall
- **Machine-bound encryption** so copied files/registry won't work on another PC
- **Offline license key validation** (no server required)
- **Three independent hidden storage locations** that self-heal if one is wiped

---

## What to implement

### 1. Dependencies

Add to `pip install` / `build.bat`:
```
cryptography
```

Add to PyInstaller `--hidden-import` flags:
```
cryptography
cryptography.fernet
cryptography.hazmat.primitives.kdf.hkdf
cryptography.hazmat.primitives.hashes
cryptography.hazmat.backends
winreg
```

---

### 2. Secrets (keep private — bake into exe, never distribute)

Define two secrets at the top of the main script. Choose unique values for each project:

```python
_LIC_SECRET = b"<project-specific-hmac-secret>"   # for license key HMAC
_KDF_SALT   = b"<project-specific-kdf-salt>"       # for storage encryption
```

---

### 3. Hidden storage locations

Use three locations that look like native Windows system files and are NOT removed by the app's own uninstaller:

```python
_APPDATA  = Path(os.environ.get("APPDATA",      str(Path.home())))
_LAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))

# Registry: disguised as a COM AppID registration
_REG_KEY = r"Software\Classes\AppID\{<project-guid>}"
_REG_VAL = "LocalService"

# File 1: disguised as a Windows jump-list file
_FILE_A = _APPDATA  / "Microsoft/Windows/Recent/AutomaticDestinations" \
                    / "<project-hex>.automaticDestinations-ms"

# File 2: disguised as a Windows thumbnail cache file
_FILE_B = _LAPPDATA / "Microsoft/Windows/Explorer" \
                    / "thumbcache_{<project-guid>}.db"
```

Replace `<project-guid>` and `<project-hex>` with a new GUID per project (use any UUID generator). The same GUID as the Inno Setup `AppId` is fine.

---

### 4. Machine fingerprint + Fernet key

```python
import base64, hashlib, sys
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes as _ch

_WIN = sys.platform == "win32"
if _WIN:
    import ctypes, ctypes.wintypes, winreg

def _machine_id() -> str:
    parts = []
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

def _make_fernet(machine_id: str) -> Fernet:
    raw = HKDF(algorithm=_ch.SHA256(), length=32,
               salt=_KDF_SALT,
               info=b"<AppName>-store-v1").derive(machine_id.encode())
    return Fernet(base64.urlsafe_b64encode(raw))

_FERNET = _make_fernet(_machine_id())   # cached at import time, HKDF is instant
```

---

### 5. Raw storage I/O

```python
def _reg_read() -> bytes | None:
    if not _WIN: return None
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        data, _ = winreg.QueryValueEx(k, _REG_VAL)
        winreg.CloseKey(k)
        return bytes(data)
    except Exception: return None

def _reg_write(data: bytes) -> None:
    if not _WIN: return
    try:
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        winreg.SetValueEx(k, _REG_VAL, 0, winreg.REG_BINARY, data)
        winreg.CloseKey(k)
    except Exception: pass

def _file_read(path: Path) -> bytes | None:
    try: return path.read_bytes()
    except Exception: return None

def _file_write(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if _WIN:
            try: ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
            except Exception: pass
    except Exception: pass
```

---

### 6. Config load / save with self-healing

```python
def _decrypt_one(raw: bytes | None) -> dict | None:
    if raw is None: return None
    try: return json.loads(_FERNET.decrypt(raw).decode())
    except (InvalidToken, Exception): return None

def _load_config() -> dict:
    blobs   = [_reg_read(), _file_read(_FILE_A), _file_read(_FILE_B)]
    records = [_decrypt_one(b) for b in blobs]
    valid   = [r for r in records if r is not None]

    if not valid:
        return {"photos_processed": 0, "licensed": False, "license_key": None}

    winner = max(valid, key=lambda c: (int(c.get("licensed", False)),
                                       c.get("photos_processed", 0)))
    encrypted = _FERNET.encrypt(json.dumps(winner).encode())
    if records[0] is None: _reg_write(encrypted)
    if records[1] is None: _file_write(_FILE_A, encrypted)
    if records[2] is None: _file_write(_FILE_B, encrypted)
    return winner

def _save_config(cfg: dict) -> None:
    encrypted = _FERNET.encrypt(json.dumps(cfg).encode())
    _reg_write(encrypted)
    _file_write(_FILE_A, encrypted)
    _file_write(_FILE_B, encrypted)
```

---

### 7. Offline license key validation (machine-agnostic)

Keys are validated by HMAC — no server needed. Machine-binding is handled by the encrypted storage, not the key itself, so customers can re-enter the same key after an OS reinstall.

```python
def _validate_key(key: str) -> bool:
    k = key.strip().upper().replace("-", "").replace(" ", "")
    if len(k) != 16: return False
    payload  = k[:8]
    expected = hmac.new(_LIC_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    return k[8:] == expected
```

---

### 8. Developer key generator (keep private, never distribute)

Store as `installer/keygen.py`:

```python
import secrets, hmac, hashlib

_SECRET = b"<same value as _LIC_SECRET in main script>"

def generate_key() -> str:
    payload  = secrets.token_hex(4).upper()
    sig      = hmac.new(_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    combined = payload + sig
    return f"{combined[0:4]}-{combined[4:8]}-{combined[8:12]}-{combined[12:16]}"

def validate_key(key: str) -> bool:
    k = key.strip().upper().replace("-", "").replace(" ", "")
    if len(k) != 16: return False
    payload  = k[:8]
    expected = hmac.new(_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    return k[8:] == expected
```

Run: `python keygen.py 10` to generate 10 keys. Send one to each paying customer.

---

### 9. Inno Setup uninstaller rule

In `setup.iss`, the `[UninstallDelete]` section must **not** list the three hidden storage locations. Only the application files in `{app}` are removed automatically. Add a comment explaining why:

```iss
; NOTE: The three hidden license/trial storage locations (registry key,
; jump-list file, Explorer cache file) are intentionally NOT removed here.
; They must survive uninstall so reinstalling cannot reset the free trial.
```

---

## Behaviour summary

| Scenario | Result |
|---|---|
| User uninstalls + reinstalls | Trial count preserved (hidden locations survive) |
| User manually deletes 1–2 of 3 locations | App silently restores them from the survivor |
| User deletes all 3 locations | Fresh start (indistinguishable from a new machine) |
| User copies files/registry to another PC | Encryption fails (wrong machine key) → fresh trial |
| User enters license key on a new OS install | Key is machine-agnostic — works immediately |
| User tries to share their key with someone else | Works on recipient's machine (acceptable for a $10 app) |

---

## Adapting for a new project

1. Generate a new UUID (e.g. from https://www.uuidgenerator.net/) — use it for `<project-guid>` in all three storage locations and in the Inno Setup `AppId`
2. Choose new random strings for `_LIC_SECRET` and `_KDF_SALT`
3. Update `_HKDF info=` to include the new app name
4. Copy `keygen.py` to the new project's `installer/` folder with the updated `_SECRET`
5. Update the free trial limit (`FREE_LIMIT`) and price as needed
