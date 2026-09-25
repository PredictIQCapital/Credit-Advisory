"""Accounts, roles, sessions.

Three roles, matching the three parties of an engagement:

    berater        the advisory (founder, later analysts): sees every case,
                   runs the analysis, releases the report to the client
    unternehmen    the SME: sees only its own case(s), fills its questionnaire,
                   uploads its documents, reads the report once released
    steuerberater  the client's tax advisor: sees only the cases it was invited
                   to, fills its questionnaire, uploads its documents

Passwords are stored as PBKDF2-SHA256 hashes (600,000 iterations, per-user
salt). Sessions are random 256-bit tokens held in memory and sent as an
HttpOnly, SameSite=Strict cookie -- a restart logs everyone out, which is the
right trade-off for a local tool.

For a hosted deployment, replace `UserStore` with the database table and the
in-memory session dict with a shared session store; the `Principal` interface
the web layer uses stays the same.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROLE_BERATER = "berater"
ROLE_UNTERNEHMEN = "unternehmen"
ROLE_STEUERBERATER = "steuerberater"
ROLES = (ROLE_BERATER, ROLE_UNTERNEHMEN, ROLE_STEUERBERATER)

# OWASP 2023 recommendation. Overridable only so the test suite stays fast;
# every stored hash records its own iteration count, so this never breaks logins.
PBKDF2_ITERATIONS = int(os.environ.get("CRA_PBKDF2_ITERATIONS", "600000"))
SESSION_TTL_SECONDS = 8 * 3600
MIN_PASSWORD_LENGTH = 8
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FAILED_LOGINS = 8
LOCKOUT_SECONDS = 300


class EmailNotConfirmed(ValueError):
    """Correct password, but the address has not been confirmed yet."""


class AuthError(ValueError):
    pass


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), hash_hex)


def normalise_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise AuthError("Ungueltige E-Mail-Adresse")
    return e


@dataclass(frozen=True)
class Principal:
    email: str
    name: str
    role: str

    @property
    def is_berater(self) -> bool:
        return self.role == ROLE_BERATER

    def public(self) -> dict:
        return {"email": self.email, "name": self.name, "role": self.role}


class UserStore:
    """Users in <root>/users.json. Small, file-based, replaceable."""

    #: The folder store sends no e-mail: no confirmation, no reset link.
    supports_email = False

    def __init__(self, root: str | Path):
        self.path = Path(root) / "users.json"
        self._lock = threading.RLock()

    def _load(self) -> dict[str, dict]:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, users: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def count(self) -> int:
        return len(self._load())

    def get(self, email: str) -> Optional[dict]:
        return self._load().get((email or "").strip().lower())

    def list(self) -> list[dict]:
        return [{k: v for k, v in u.items() if k != "password_hash"} for u in self._load().values()]

    def create(self, email: str, name: str, role: str, password: str) -> Principal:
        if role not in ROLES:
            raise AuthError(f"Unbekannte Rolle '{role}'")
        email = normalise_email(email)
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        name = (name or "").strip() or email
        with self._lock:
            users = self._load()
            if email in users:
                raise AuthError("Fuer diese E-Mail-Adresse besteht bereits ein Konto")
            users[email] = {
                "email": email,
                "name": name,
                "role": role,
                "password_hash": hash_password(password),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            self._save(users)
        return Principal(email, name, role)

    def set_password(self, email: str, password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        with self._lock:
            users = self._load()
            key = email.strip().lower()
            if key not in users:
                raise AuthError("Konto nicht gefunden")
            users[key]["password_hash"] = hash_password(password)
            self._save(users)

    def delete(self, email: str) -> None:
        with self._lock:
            users = self._load()
            users.pop((email or "").strip().lower(), None)
            self._save(users)

    def authenticate(self, email: str, password: str) -> Optional[Principal]:
        u = self.get(email)
        # Hash even for unknown users, so response time does not reveal
        # which e-mail addresses have accounts.
        stored = u["password_hash"] if u else hash_password("x" * 12, b"\x00" * 16)
        ok = verify_password(password or "", stored)
        if u and ok:
            return Principal(u["email"], u["name"], u["role"])
        return None


class SessionManager:
    def __init__(self, ttl: int = SESSION_TTL_SECONDS):
        self.ttl = ttl
        self._sessions: dict[str, tuple[Principal, float]] = {}
        self._failures: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def create(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = (principal, time.time() + self.ttl)
        return token

    def get(self, token: Optional[str]) -> Optional[Principal]:
        if not token:
            return None
        with self._lock:
            entry = self._sessions.get(token)
            if not entry:
                return None
            principal, expires = entry
            if expires < time.time():
                del self._sessions[token]
                return None
            self._sessions[token] = (principal, time.time() + self.ttl)   # sliding
            return principal

    def destroy(self, token: Optional[str]) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def destroy_all(self, email: str) -> None:
        """Log an account out everywhere (after a password change or reset)."""
        with self._lock:
            for t in [t for t, (p, _) in self._sessions.items() if p.email == email]:
                del self._sessions[t]

    # -- brute-force brake -------------------------------------------------
    def locked_out(self, email: str) -> bool:
        with self._lock:
            n, until = self._failures.get(email, (0, 0.0))
            return n >= MAX_FAILED_LOGINS and until > time.time()

    def record_failure(self, email: str) -> None:
        with self._lock:
            n, _ = self._failures.get(email, (0, 0.0))
            self._failures[email] = (n + 1, time.time() + LOCKOUT_SECONDS)

    def clear_failures(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)


# ---------------------------------------------------------------------------
# Case membership: who may see which case
# ---------------------------------------------------------------------------


def case_members(meta: dict) -> dict[str, list[str]]:
    m = meta.get("members") or {}
    return {
        ROLE_UNTERNEHMEN: list(m.get(ROLE_UNTERNEHMEN, [])),
        ROLE_STEUERBERATER: list(m.get(ROLE_STEUERBERATER, [])),
    }


def can_access_case(principal: Principal, meta: dict) -> bool:
    if principal.is_berater:
        return True
    return principal.email in case_members(meta).get(principal.role, [])
