"""Kept-alive connections to Supabase: reused while warm, replaced after a pause."""

from __future__ import annotations

from credit_readiness import supa


class FakeConn:
    made = []

    def __init__(self, host, timeout):
        self.closed = False
        FakeConn.made.append(self)

    def close(self):
        self.closed = True


def test_idle_connections_are_not_reused(monkeypatch):
    FakeConn.made = []
    clock = [1000.0]
    monkeypatch.setattr(supa.http.client, "HTTPSConnection", FakeConn)
    monkeypatch.setattr(supa.time, "monotonic", lambda: clock[0])
    sb = supa.Supabase("https://x.supabase.co", "sb_secret_x")

    first, reused = sb._conn()
    assert not reused
    clock[0] += 2                                # the next call of the same page
    assert sb._conn() == (first, True)
    clock[0] += supa.IDLE_MAX + 1                # the instance slept in between
    fresh, reused = sb._conn()
    assert fresh is not first and first.closed and not reused
    assert len(FakeConn.made) == 2
