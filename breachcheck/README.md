# BreachCheck

A **local-only** breach-lookup tool for **authorized** security / red-team work.
It's a thin, self-hosted UI over two official APIs you authenticate with **your own keys**:

- **LeakCheck Pro** — email / username / phone / hash / name (keyword) / auto-detect lookups
- **Have I Been Pwned (HIBP)** — email breach lookups and password exposure checks

Everything runs on `127.0.0.1`. There is no telemetry, no analytics, and no outbound
traffic except to the official LeakCheck and HIBP endpoints.

> ⚠️ **Use only against accounts/data you are authorized to investigate.** This queries
> paid breach-intelligence APIs under your own account and quota.

---

## Install

```bash
pip install -r requirements.txt
```

(Python 3.9+. A virtualenv is recommended: `python -m venv .venv && source .venv/bin/activate`.)

## Run

```bash
python app.py
```

Then open **http://127.0.0.1:8787** in your browser.

(Equivalent: `uvicorn app:app --host 127.0.0.1 --port 8787`.)

## Enter your keys

On first launch you'll land on the **Settings** page. Paste:

- **LeakCheck Pro key** (required, 40+ characters)
- **HIBP key** (optional — only needed for email breach lookups; the password
  k-anonymity check needs no key)

Keys are held **in memory for the session**. Tick **"persist to local .env"** only if
you want them saved to a local `.env` file (it's gitignored and written `chmod 600`).
Use **WIPE KEYS** to clear them from memory and delete the `.env`.

Keys are never hardcoded, never logged, and never sent anywhere except the official APIs.

## Search

Pick a type and run:

| Type | Backend | Notes |
|------|---------|-------|
| Auto / Reverse | LeakCheck | Paste anything (email, phone, username, name, hash) — the API detects the type. This is the "reverse / mixed" search. |
| Email | LeakCheck (+ optional HIBP) | Tick "also query HIBP" to append HIBP breach records. |
| Username | LeakCheck | |
| Phone number | LeakCheck | Digits only, e.g. `15551234567`. |
| Name / keyword | LeakCheck | |
| Hash | LeakCheck | md5 / sha* credential hash. |
| Password | **HIBP only** | k-anonymity check — see below. |

Full records are pretty-printed, including any passwords present in the dump (shown in red).

### Password checks are safe by design

The **Password** type does **not** do a reverse "who used this password" lookup — that's a
LeakCheck Enterprise feature and a targeting vector, so it's intentionally not built.
Instead it uses **HIBP Pwned Passwords k-anonymity**: your password is SHA-1 hashed
**locally**, and only the **first 5 characters of the hash** are sent to HIBP. The full
password and full hash never leave your machine. Passwords are also never written to search history.

## Scope / limitations

This tool deliberately stays inside what a regular **LeakCheck Pro** plan returns. It does
**not** implement Enterprise-only features: reverse-password search, domain-wide search, or
origin lookups. Those calls aren't wired up; if the API rejects a query for plan reasons,
the UI reports it cleanly.

## Search history

Recent searches are stored **only in your browser's `localStorage`** (never server-side,
never passwords). Clear them anytime with the **clear** link.

## Files

```
breachcheck/
├─ app.py            # FastAPI backend (key store + API calls)
├─ requirements.txt
├─ .env.example      # optional persistence template
├─ .gitignore        # ignores .env, venv, caches
├─ README.md
└─ static/
   ├─ index.html     # cyberpunk UI
   ├─ styles.css
   └─ app.js
```
