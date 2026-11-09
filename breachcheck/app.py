"""
BreachCheck - local-only breach lookup tool for authorized security / red-team use.

Design principles baked in:
  * API keys live only in memory for the session, or (optionally) in a local
    .gitignored .env file. They are never hardcoded and never logged.
  * The ONLY place keys are ever sent is the official LeakCheck / HIBP APIs.
  * No telemetry, no analytics, no outbound calls except those two APIs.
  * Everything is served on localhost.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv, set_key
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from leakcheck import LeakCheckAPI_v2

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ENV_PATH = BASE_DIR / ".env"

# Load any persisted keys from a local .env (if the user chose to persist them).
load_dotenv(ENV_PATH)

# ---------------------------------------------------------------------------
# In-memory key store. This is the single source of truth at runtime.
# We seed it from the environment on boot but never write it to logs.
# ---------------------------------------------------------------------------
KEYS: dict[str, Optional[str]] = {
    "leakcheck": os.getenv("LEAKCHECK_APIKEY") or None,
    "hibp": os.getenv("HIBP_APIKEY") or None,
}

# The leakcheck library itself reads LEAKCHECK_APIKEY from the env and would
# override any key we pass explicitly. Clear it so our in-memory key always wins.
os.environ.pop("LEAKCHECK_APIKEY", None)

HIBP_USER_AGENT = "BreachCheck-LocalTool"

# Query types we expose. Reverse-password / domain / origin (Enterprise-only)
# are deliberately NOT here.
LEAKCHECK_TYPES = {"auto", "email", "username", "phone", "hash", "keyword"}

app = FastAPI(title="BreachCheck", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SettingsIn(BaseModel):
    leakcheck_key: Optional[str] = None
    hibp_key: Optional[str] = None
    persist: bool = False


class SearchIn(BaseModel):
    query: str
    type: str = "auto"
    limit: int = 100


class PasswordIn(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _classify_leakcheck_error(msg: str) -> tuple[int, str]:
    """Map a raw leakcheck error string to (http_status, friendly_message)."""
    low = msg.lower()
    if "not found" in low:
        # Treat 'not found' as a clean empty result, handled by caller.
        return 200, msg
    if "invalid" in low and "key" in low:
        return 401, "LeakCheck rejected the API key (invalid or unauthorized)."
    if "limit" in low and "reached" in low or "quota" in low or "exceeded" in low:
        return 429, "LeakCheck quota or rate limit reached. Try again later."
    if "429" in low or "too many" in low:
        return 429, "LeakCheck rate limit hit. Slow down and retry shortly."
    if "enterprise" in low or "plan" in low:
        return 403, "That lookup requires a higher LeakCheck plan than Pro."
    return 502, f"LeakCheck error: {msg}"


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Settings / status
# ---------------------------------------------------------------------------
@app.get("/api/status")
def status() -> dict[str, Any]:
    """Report which keys are configured. Never returns the key values."""
    return {
        "ok": True,
        "leakcheck_set": bool(KEYS["leakcheck"]),
        "hibp_set": bool(KEYS["hibp"]),
        "persisted": ENV_PATH.exists(),
    }


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    lc = (body.leakcheck_key or "").strip()
    hibp = (body.hibp_key or "").strip()

    if lc:
        if len(lc) < 40:
            return _err("LeakCheck API key looks too short (expected 40+ characters).")
        KEYS["leakcheck"] = lc
    if hibp:
        KEYS["hibp"] = hibp

    # Optional local persistence to a gitignored .env file.
    if body.persist:
        ENV_PATH.touch(exist_ok=True)
        try:
            os.chmod(ENV_PATH, 0o600)  # keep it readable only by the owner
        except OSError:
            pass
        if KEYS["leakcheck"]:
            set_key(str(ENV_PATH), "LEAKCHECK_APIKEY", KEYS["leakcheck"])
        if KEYS["hibp"]:
            set_key(str(ENV_PATH), "HIBP_APIKEY", KEYS["hibp"])

    return status()


@app.post("/api/settings/clear")
def clear_settings():
    """Wipe keys from memory and remove the persisted .env if present."""
    KEYS["leakcheck"] = None
    KEYS["hibp"] = None
    if ENV_PATH.exists():
        ENV_PATH.unlink()
    return status()


# ---------------------------------------------------------------------------
# LeakCheck search (email / username / phone / hash / keyword / auto)
# ---------------------------------------------------------------------------
@app.post("/api/search")
def search(body: SearchIn):
    if not KEYS["leakcheck"]:
        return _err("No LeakCheck API key configured. Add it in Settings.", 401)

    qtype = (body.type or "auto").lower()
    if qtype not in LEAKCHECK_TYPES:
        return _err(f"Unsupported search type '{qtype}'.")

    query = body.query.strip()
    if not query:
        return _err("Query is empty.")

    limit = max(1, min(int(body.limit or 100), 1000))

    try:
        client = LeakCheckAPI_v2(api_key=KEYS["leakcheck"])
    except ValueError as e:
        return _err(str(e), 401)

    # query_type=None lets the API auto-detect; that is our "auto" mode.
    api_type = None if qtype == "auto" else qtype

    try:
        result = client.lookup(query=query, query_type=api_type, limit=limit)
    except ValueError as e:
        http_status, friendly = _classify_leakcheck_error(str(e))
        if http_status == 200:  # "not found" => clean empty result
            return {"ok": True, "count": 0, "results": [], "source": "leakcheck"}
        return _err(friendly, http_status)
    except requests.exceptions.RequestException:
        return _err("Could not reach LeakCheck (network error).", 502)

    records = result if isinstance(result, list) else []
    return {
        "ok": True,
        "count": len(records),
        "results": records,
        "source": "leakcheck",
    }


# ---------------------------------------------------------------------------
# HIBP - breached account (email)
# ---------------------------------------------------------------------------
@app.post("/api/hibp/email")
def hibp_email(body: SearchIn):
    if not KEYS["hibp"]:
        return _err("No HIBP API key configured. Add it in Settings.", 401)

    account = body.query.strip()
    if not account:
        return _err("Email is empty.")

    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{requests.utils.quote(account)}"
    try:
        resp = requests.get(
            url,
            params={"truncateResponse": "false"},
            headers={"hibp-api-key": KEYS["hibp"], "user-agent": HIBP_USER_AGENT},
            timeout=20,
        )
    except requests.exceptions.RequestException:
        return _err("Could not reach HIBP (network error).", 502)

    if resp.status_code == 404:
        return {"ok": True, "count": 0, "results": [], "source": "hibp"}
    if resp.status_code == 401:
        return _err("HIBP rejected the API key (invalid or unauthorized).", 401)
    if resp.status_code == 429:
        retry = resp.headers.get("retry-after", "a few")
        return _err(f"HIBP rate limit hit. Retry after {retry} seconds.", 429)
    if resp.status_code != 200:
        return _err(f"HIBP error (HTTP {resp.status_code}).", 502)

    breaches = resp.json()
    return {"ok": True, "count": len(breaches), "results": breaches, "source": "hibp"}


# ---------------------------------------------------------------------------
# HIBP - Pwned Passwords via k-anonymity.
# The full password NEVER leaves this machine: we SHA-1 it locally and send
# only the first 5 hex chars of the hash. No API key required.
# ---------------------------------------------------------------------------
@app.post("/api/hibp/password")
def hibp_password(body: PasswordIn):
    if not body.password:
        return _err("Password is empty.")

    sha1 = hashlib.sha1(body.password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            headers={"user-agent": HIBP_USER_AGENT, "Add-Padding": "true"},
            timeout=20,
        )
    except requests.exceptions.RequestException:
        return _err("Could not reach HIBP Pwned Passwords (network error).", 502)

    if resp.status_code != 200:
        return _err(f"HIBP Pwned Passwords error (HTTP {resp.status_code}).", 502)

    count = 0
    for line in resp.text.splitlines():
        if ":" not in line:
            continue
        line_suffix, line_count = line.split(":", 1)
        if line_suffix.strip().upper() == suffix:
            try:
                count = int(line_count.strip())
            except ValueError:
                count = 0
            break

    return {
        "ok": True,
        "pwned": count > 0,
        "count": count,
        "source": "hibp-passwords",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
