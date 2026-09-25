"""Account self-service: change password, confirm e-mail, forgot password."""

from __future__ import annotations

import threading

import pytest

from credit_readiness.auth import ROLE_BERATER, EmailNotConfirmed, Principal, UserStore
from credit_readiness.auth_supabase import SupabaseUserStore
from credit_readiness.casefile import LocalCaseStore
from credit_readiness.webapp.server import make_server

from tests.test_portal import TODAY, Client, _register, env  # noqa: F401  (fixture)


# ------------------------------------------------------------------ change password


def test_change_password_needs_the_current_one_and_ends_other_sessions(env):  # noqa: F811
    _, _, base = env
    c, _ = _register(base)
    other = Client(base)
    other.login("anna@test.de", "anna-pass-1")

    assert c.call("POST", "/api/auth/password",
                  {"current_password": "falsch", "new_password": "neues-pass-9"})[0] == 400
    assert c.call("POST", "/api/auth/password",
                  {"current_password": "anna-pass-1", "new_password": "anna-pass-1"})[0] == 400
    assert c.call("POST", "/api/auth/password",
                  {"current_password": "anna-pass-1", "new_password": "kurz"})[0] == 400
    assert c.call("POST", "/api/auth/password",
                  {"current_password": "anna-pass-1", "new_password": "neues-pass-9"})[0] == 200

    assert c.call("GET", "/api/cases")[0] == 200          # this session continues
    assert other.call("GET", "/api/cases")[0] == 401      # the other one ended
    assert Client(base).call("POST", "/api/auth/login",
                             {"email": "anna@test.de", "password": "anna-pass-1"})[0] == 401
    Client(base).login("anna@test.de", "neues-pass-9")


def test_change_password_needs_a_login(env):  # noqa: F811
    _, _, base = env
    assert Client(base).call("POST", "/api/auth/password",
                             {"current_password": "a", "new_password": "bbbbbbbbb"})[0] == 401


def test_folder_store_offers_no_email_flows(env):  # noqa: F811
    _, _, base = env
    c = Client(base)
    assert c.call("GET", "/api/meta")[1]["email_auth"] is False
    for path in ("/api/auth/forgot", "/api/auth/resend", "/api/auth/reset"):
        assert c.call("POST", path, {"email": "a@test.de"})[0] == 501


# ------------------------------------------------------------------ with e-mail (Supabase stand-in)


class EmailUsers(UserStore):
    """The folder store plus what Supabase Auth adds: confirmation and reset e-mails."""

    supports_email = True

    def __init__(self, root):
        super().__init__(root)
        self.unconfirmed: set[str] = set()
        self.sent: list[tuple[str, str, str]] = []           # (kind, email, redirect)
        self.tokens: dict[str, str] = {}

    def signup(self, email, name, role, password, redirect_to=""):
        p = self.create(email, name, role, password)
        self.unconfirmed.add(p.email)
        self.sent.append(("confirm", p.email, redirect_to))
        return p, False

    def authenticate(self, email, password):
        p = super().authenticate(email, password)
        if p and p.email in self.unconfirmed:
            raise EmailNotConfirmed(email)
        return p

    def resend_confirmation(self, email, redirect_to=""):
        if email in self.unconfirmed:
            self.sent.append(("confirm", email, redirect_to))

    def send_password_reset(self, email, redirect_to=""):
        if self.get(email):
            self.tokens["tok-" + email] = email
            self.sent.append(("reset", email, redirect_to))

    def reset_with_token(self, access_token, password):
        from credit_readiness.auth import AuthError
        email = self.tokens.pop(access_token, None)
        if not email:
            raise AuthError("Der Link ist abgelaufen. Bitte fordern Sie einen neuen an.")
        self.set_password(email, password)
        return email


@pytest.fixture
def mail_env(tmp_path):
    store = LocalCaseStore(tmp_path / "clients")
    users = EmailUsers(store.root)
    users.create("berater@test.de", "Berater", ROLE_BERATER, "berater-pass")
    srv = make_server(store, port=0, today=TODAY, users=users)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield users, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def test_registration_waits_for_the_confirmation(mail_env):
    users, base = mail_env
    c = Client(base)
    assert c.call("GET", "/api/meta")[1]["email_auth"] is True
    status, body = c.call("POST", "/api/auth/register", {
        "company_name": "Neu GmbH", "name": "Nora Neu", "email": "nora@test.de",
        "password": "nora-pass-1", "consent": True})
    assert status == 201 and body["verify_email"] is True and "user" not in body
    assert c.call("GET", "/api/cases")[0] == 401                  # no session yet
    kind, email, redirect = users.sent[-1]
    assert (kind, email) == ("confirm", "nora@test.de") and redirect.endswith("/app")

    status, body = c.call("POST", "/api/auth/login", {"email": "nora@test.de", "password": "nora-pass-1"})
    assert status == 403 and body["unconfirmed"] is True
    assert c.call("POST", "/api/auth/resend", {"email": "nora@test.de"})[0] == 200
    assert len([s for s in users.sent if s[0] == "confirm"]) == 2

    users.unconfirmed.discard("nora@test.de")                      # the link was clicked
    c.login("nora@test.de", "nora-pass-1")
    assert c.call("GET", "/api/cases")[1][0]["company_name"] == "Neu GmbH"


def test_forgot_password_never_reveals_whether_an_account_exists(mail_env):
    users, base = mail_env
    c = Client(base)
    assert c.call("POST", "/api/auth/forgot", {"email": "berater@test.de"}) == (200, {"ok": True})
    assert c.call("POST", "/api/auth/forgot", {"email": "niemand@test.de"}) == (200, {"ok": True})
    assert [s[1] for s in users.sent if s[0] == "reset"] == ["berater@test.de"]


def test_reset_link_sets_a_new_password_once(mail_env):
    users, base = mail_env
    logged_in = Client(base)
    logged_in.login("berater@test.de", "berater-pass")
    c = Client(base)
    c.call("POST", "/api/auth/forgot", {"email": "berater@test.de"})
    token = "tok-berater@test.de"
    assert c.call("POST", "/api/auth/reset", {"access_token": token, "password": "ganz-neu-77"})[0] == 200
    assert logged_in.call("GET", "/api/cases")[0] == 401          # logged out everywhere
    assert c.call("POST", "/api/auth/reset", {"access_token": token, "password": "noch-neuer-8"})[0] == 400
    Client(base).login("berater@test.de", "ganz-neu-77")


# ------------------------------------------------------------------ Supabase store logic


class FakeSupabase:
    def __init__(self, signup_response):
        self.signup_response = signup_response
        self.inserted = []

    def select(self, table, query=""):
        return []

    def sign_up(self, email, password, name, redirect_to=""):
        return self.signup_response

    def insert(self, table, rows, **kw):
        self.inserted.append((table, rows))
        return []


@pytest.mark.parametrize("response, confirmed", [
    ({"id": "u1", "email": "a@x.de", "identities": [{"id": "i"}]}, False),              # confirm by e-mail
    ({"access_token": "t", "user": {"id": "u1", "identities": [{"id": "i"}]}}, True),   # confirmation off
])
def test_supabase_signup_reads_whether_confirmation_is_pending(response, confirmed):
    sb = FakeSupabase(response)
    p, ok = SupabaseUserStore(sb).signup("A@x.de", "Anna A", "unternehmen", "passwort-1")
    assert p == Principal("a@x.de", "Anna A", "unternehmen") and ok is confirmed
    assert sb.inserted[0][0] == "users" and sb.inserted[0][1]["auth_id"] == "u1"


def test_supabase_signup_of_a_known_address_is_refused():
    from credit_readiness.auth import AuthError
    sb = FakeSupabase({"id": "fake", "email": "a@x.de", "identities": []})
    with pytest.raises(AuthError):
        SupabaseUserStore(sb).signup("a@x.de", "Anna A", "unternehmen", "passwort-1")
    assert sb.inserted == []
