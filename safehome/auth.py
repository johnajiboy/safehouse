"""Officer accounts and sign-in sessions.

Passwords are stored only as scrypt hashes, and session tokens only as SHA-256
hashes, so a copy of the database cannot be used to sign in.

Add or remove an officer from the project root:
    python -m safehome.auth add <username>
    python -m safehome.auth remove <username>
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sys
from datetime import datetime, timedelta

from . import config, store

DEMO_OFFICER = "demo"  # reserved: only demo mode can sign in as this name
SESSION_HOURS = 12
MIN_PASSWORD_LENGTH = 10
MAX_FAILURES = 5  # failed sign-ins allowed per username within FAILURE_WINDOW
FAILURE_WINDOW = timedelta(minutes=15)

_failures: dict[str, list[datetime]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    attempt = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(attempt.hex(), digest)


def add_officer(username: str, password: str) -> None:
    if username == DEMO_OFFICER:
        raise ValueError(f'"{DEMO_OFFICER}" is reserved for demo mode')
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters")
    with store.connect() as db:
        db.execute("INSERT OR REPLACE INTO officers (username, password_hash) VALUES (?, ?)",
                   (username, hash_password(password)))


def ensure_default_officer() -> bool:
    """Create the officer named in .env if there are no officer accounts yet. True if one was created."""
    if not (config.OFFICER_USERNAME and config.OFFICER_PASSWORD):
        return False
    with store.connect() as db:
        if db.execute("SELECT COUNT(*) FROM officers").fetchone()[0]:
            return False
    try:
        add_officer(config.OFFICER_USERNAME, config.OFFICER_PASSWORD)
    except ValueError as error:
        print(f"Default officer not created: {error}. Check OFFICER_USERNAME and OFFICER_PASSWORD in .env.")
        return False
    store.log("Officer", f"Created the default officer account {config.OFFICER_USERNAME} from .env")
    return True


def remove_officer(username: str) -> None:
    with store.connect() as db:
        db.execute("DELETE FROM officers WHERE username = ?", (username,))
        db.execute("DELETE FROM sessions WHERE username = ?", (username,))


class TooManyAttempts(Exception):
    pass


def sign_in(username: str, password: str, now: datetime | None = None) -> str | None:
    """Return a new session token, or None if the username or password is wrong."""
    now = now or datetime.now()
    recent = [t for t in _failures.get(username, []) if now - t < FAILURE_WINDOW]
    if len(recent) >= MAX_FAILURES:
        raise TooManyAttempts("Too many failed sign-ins. Try again in 15 minutes.")
    with store.connect() as db:
        row = db.execute("SELECT password_hash FROM officers WHERE username = ?", (username,)).fetchone()
    if row is None or not check_password(password, row["password_hash"]):
        _failures[username] = [*recent, now]
        return None
    _failures.pop(username, None)
    return _start_session(username, now)


def sign_in_demo(now: datetime | None = None) -> str | None:
    """Sign in as the demo officer without a password, but only while demo mode is on."""
    if not config.DEMO_MODE:
        return None
    return _start_session(DEMO_OFFICER, now or datetime.now())


def is_demo(username: str | None) -> bool:
    return config.DEMO_MODE and username == DEMO_OFFICER


def officer_for(token: str | None, now: datetime | None = None) -> str | None:
    """The signed-in officer for a session token, or None if it is missing or expired."""
    if not token:
        return None
    with store.connect() as db:
        row = db.execute("SELECT username, expires_at FROM sessions WHERE token_hash = ?",
                         (_token_hash(token),)).fetchone()
    if row is None or datetime.fromisoformat(row["expires_at"]) <= (now or datetime.now()):
        return None
    if row["username"] == DEMO_OFFICER and not config.DEMO_MODE:
        return None  # demo sessions end as soon as demo mode is turned off
    return row["username"]


def _start_session(username: str, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    with store.connect() as db:
        db.execute("INSERT INTO sessions (token_hash, username, expires_at) VALUES (?, ?, ?)",
                   (_token_hash(token), username, (now + timedelta(hours=SESSION_HOURS)).isoformat()))
    store.log("Officer", f"{username} signed in" + (" (demo mode)" if username == DEMO_OFFICER else ""))
    return token


def sign_out(token: str | None) -> None:
    if token:
        with store.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def main(args: list[str]) -> None:
    import getpass

    if len(args) != 2 or args[0] not in ("add", "remove"):
        sys.exit("Usage: python -m safehome.auth add|remove <username>")
    action, username = args
    if action == "remove":
        remove_officer(username)
        print(f"Removed {username}")
        return
    password = getpass.getpass(f"Password for {username}: ")
    if password != getpass.getpass("Type it again: "):
        sys.exit("The passwords don't match")
    try:
        add_officer(username, password)
    except ValueError as error:
        sys.exit(str(error))
    print(f"Added {username}")


if __name__ == "__main__":
    main(sys.argv[1:])
