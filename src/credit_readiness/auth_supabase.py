"""Accounts on Supabase Auth, sessions and lockouts in the database.

SupabaseUserStore has the UserStore interface; passwords are held and checked
by Supabase Auth, while app.users keeps name and role (the role decides
access, so it must not live in metadata the user can edit).

DbSessionManager has the SessionManager interface. Serverless functions keep
no memory between requests, so sessions and failed-login counts live in
app.sessions / app.login_failures. Only a SHA-256 of the cookie token is
stored: a leaked table does not hand out live sessions.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from .auth import (
    LOCKOUT_SECONDS,
    MAX_FAILED_LOGINS,
    MIN_PASSWORD_LENGTH,
    ROLES,
    SESSION_TTL_SECONDS,
    AuthError,
    Principal,
    normalise_email,
)
from .supa import Supabase, SupabaseError, q

#: A session's expiry is pushed forward at most this often, not on every request.
SLIDE_EVERY_SECONDS = 300


def _log_mail_failure(kind: str, e: SupabaseError) -> None:
    """A mail Supabase could not send (wrong SMTP password, say) -- for the server log only."""
    import sys
    print(f"[auth] {kind} e-mail not sent: HTTP {e.status} {e.body}", file=sys.stderr)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class SupabaseUserStore:
    #: Supabase Auth sends confirmation and password-reset e-mails.
    supports_email = True

    def __init__(self, client: Supabase):
        self.sb = client

    # -- self-service ------------------------------------------------------
    def signup(self, email: str, name: str, role: str, password: str,
               redirect_to: str = "") -> tuple[Principal, bool]:
        """Register through Supabase Auth, which e-mails a confirmation link.

        Returns (principal, confirmed). `confirmed` is False while the link
        has not been clicked -- unless "Confirm email" is switched off in the
        project, in which case Supabase confirms at once.
        """
        if role not in ROLES:
            raise AuthError(f"Unbekannte Rolle '{role}'")
        email = normalise_email(email)
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        name = (name or "").strip() or email
        if self.get(email):
            raise AuthError("Fuer diese E-Mail-Adresse besteht bereits ein Konto")
        try:
            out = self.sb.sign_up(email, password, name, redirect_to)
        except SupabaseError as e:
            if e.status == 422:
                raise AuthError(str(e.body.get("msg") if isinstance(e.body, dict) else e)) from None
            if e.status == 429:
                raise AuthError("Zu viele Anmeldungen in kurzer Zeit. Bitte spaeter erneut versuchen.") from None
            raise
        user = out.get("user") or out
        # Supabase answers an already-registered address with an empty
        # identity list instead of an error (so that sign-up cannot be used to
        # probe for accounts).
        if not user.get("id") or user.get("identities") == []:
            raise AuthError("Fuer diese E-Mail-Adresse besteht bereits ein Konto")
        self.sb.insert("users", {"email": email, "name": name, "role": role, "auth_id": user["id"]},
                       returning=False)
        confirmed = bool(out.get("access_token") or user.get("email_confirmed_at") or user.get("confirmed_at"))
        return Principal(email, name, role), confirmed

    def resend_confirmation(self, email: str, redirect_to: str = "") -> None:
        try:
            self.sb.resend_confirmation((email or "").strip().lower(), redirect_to)
        except SupabaseError as e:
            if e.status == 429:
                raise AuthError("Bitte einige Minuten warten, bevor Sie erneut senden.") from None
            # The visitor gets no hint (it must not reveal accounts); the log does.
            _log_mail_failure("confirmation", e)

    def send_password_reset(self, email: str, redirect_to: str = "") -> None:
        try:
            self.sb.send_password_reset((email or "").strip().lower(), redirect_to)
        except SupabaseError as e:
            if e.status == 429:
                raise AuthError("Bitte einige Minuten warten, bevor Sie erneut senden.") from None
            _log_mail_failure("password reset", e)

    def reset_with_token(self, access_token: str, password: str) -> str:
        """Set the password from a reset link. Returns the account's e-mail."""
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        try:
            user = self.sb.set_password_with_token(access_token, password)
        except SupabaseError as e:
            if e.status in (401, 403):
                raise AuthError("Der Link ist abgelaufen. Bitte fordern Sie einen neuen an.") from None
            if e.status == 422:
                raise AuthError("Bitte ein anderes Passwort waehlen (nicht das bisherige, mind. "
                                f"{MIN_PASSWORD_LENGTH} Zeichen).") from None
            raise
        return user["email"]

    def count(self) -> int:
        return len(self.sb.select("users", "select=email"))

    def get(self, email: str) -> Optional[dict]:
        rows = self.sb.select("users", f"email=eq.{q((email or '').strip().lower())}"
                                       "&select=email,name,role,created_at,auth_id")
        return rows[0] if rows else None

    def list(self) -> list[dict]:
        return self.sb.select("users", "select=email,name,role,created_at&order=created_at.asc")

    def create(self, email: str, name: str, role: str, password: str) -> Principal:
        if role not in ROLES:
            raise AuthError(f"Unbekannte Rolle '{role}'")
        email = normalise_email(email)
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        name = (name or "").strip() or email
        if self.get(email):
            raise AuthError("Fuer diese E-Mail-Adresse besteht bereits ein Konto")
        try:
            user = self.sb.admin_create_user(email, password, name)
        except SupabaseError as e:
            if e.status == 422:
                raise AuthError("Fuer diese E-Mail-Adresse besteht bereits ein Konto") from None
            raise
        try:
            self.sb.insert("users", {"email": email, "name": name, "role": role, "auth_id": user["id"]},
                           returning=False)
        except SupabaseError:
            self.sb.admin_delete_user(user["id"])     # no Auth user without a profile
            raise
        return Principal(email, name, role)

    def set_password(self, email: str, password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben")
        u = self.get(email)
        if not u or not u.get("auth_id"):
            raise AuthError("Konto nicht gefunden")
        self.sb.admin_update_user(u["auth_id"], password=password)

    def delete(self, email: str) -> None:
        u = self.get(email)
        if not u:
            return
        if u.get("auth_id"):
            self.sb.admin_delete_user(u["auth_id"])    # cascades to app.users and sessions
        self.sb.delete("users", f"email=eq.{q(u['email'])}")

    def authenticate(self, email: str, password: str) -> Optional[Principal]:
        email = (email or "").strip().lower()
        if not email or not password:
            return None
        if not self.sb.sign_in(email, password):
            return None
        u = self.get(email)
        return Principal(u["email"], u["name"], u["role"]) if u else None


class DbSessionManager:
    def __init__(self, client: Supabase, ttl: int = SESSION_TTL_SECONDS):
        self.sb = client
        self.ttl = ttl

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(32)
        self.sb.insert("sessions", {"token_sha256": self._hash(token), "email": principal.email,
                                    "expires_at": _iso(_now() + timedelta(seconds=self.ttl))}, returning=False)
        return token

    def get(self, token: Optional[str]) -> Optional[Principal]:
        if not token:
            return None
        h = self._hash(token)
        rows = self.sb.select("sessions", f"token_sha256=eq.{h}&select=expires_at,users(email,name,role)")
        if not rows or not rows[0].get("users"):
            return None
        expires = datetime.fromisoformat(rows[0]["expires_at"])
        now = _now()
        if expires < now:
            self.sb.delete("sessions", f"token_sha256=eq.{h}")
            return None
        if (now + timedelta(seconds=self.ttl) - expires).total_seconds() > SLIDE_EVERY_SECONDS:
            self.sb.update("sessions", f"token_sha256=eq.{h}",
                           {"expires_at": _iso(now + timedelta(seconds=self.ttl))})
        u = rows[0]["users"]
        return Principal(u["email"], u["name"], u["role"])

    def destroy(self, token: Optional[str]) -> None:
        if token:
            self.sb.delete("sessions", f"token_sha256=eq.{self._hash(token)}")

    def destroy_all(self, email: str) -> None:
        """Log an account out everywhere (after a password change or reset)."""
        self.sb.delete("sessions", f"email=eq.{q(email)}")

    # -- brute-force brake -------------------------------------------------
    def _recent(self, email: str) -> list[dict]:
        since = _iso(_now() - timedelta(seconds=LOCKOUT_SECONDS))
        return self.sb.select("login_failures", f"email=eq.{q(email)}&at=gte.{q(since)}&select=id")

    def locked_out(self, email: str) -> bool:
        return len(self._recent(email)) >= MAX_FAILED_LOGINS

    def record_failure(self, email: str) -> None:
        self.sb.insert("login_failures", {"email": email}, returning=False)

    def clear_failures(self, email: str) -> None:
        self.sb.delete("login_failures", f"email=eq.{q(email)}")
