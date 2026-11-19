"""Temporary DNS failures (EAI_AGAIN) are retried with backoff; others are not."""

import socket

import pytest

from app.core import dns_retry


def _flaky(failures: int, errno: int = socket.EAI_AGAIN):
    calls: list[str] = []

    def getaddrinfo(host: str, port: int) -> list[str]:
        calls.append(host)
        if len(calls) <= failures:
            raise socket.gaierror(errno, "Temporary failure in name resolution")
        return [f"{host}:{port}"]

    return getaddrinfo, calls


def test_temporary_failures_are_retried_with_backoff():
    getaddrinfo, calls = _flaky(failures=2)
    waits: list[float] = []

    lookup = dns_retry.retrying(getaddrinfo, delays=(0.5, 1.0, 2.0), sleep=waits.append)

    assert lookup("snipeit.home.example", 443) == ["snipeit.home.example:443"]
    assert len(calls) == 3
    assert waits == [0.5, 1.0]


def test_gives_up_after_the_last_delay():
    getaddrinfo, calls = _flaky(failures=10)
    waits: list[float] = []

    lookup = dns_retry.retrying(getaddrinfo, delays=(0.5, 1.0), sleep=waits.append)

    with pytest.raises(socket.gaierror) as caught:
        lookup("vault.home.example", 443)
    assert caught.value.errno == socket.EAI_AGAIN
    assert len(calls) == 3  # first try + one per delay
    assert waits == [0.5, 1.0]


def test_an_unknown_name_fails_at_once():
    getaddrinfo, calls = _flaky(failures=1, errno=socket.EAI_NONAME)
    waits: list[float] = []

    lookup = dns_retry.retrying(getaddrinfo, sleep=waits.append)

    with pytest.raises(socket.gaierror):
        lookup("typo.example", 443)
    assert len(calls) == 1
    assert waits == []


def test_install_wraps_socket_getaddrinfo_once(monkeypatch: pytest.MonkeyPatch):
    getaddrinfo, calls = _flaky(failures=1)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(dns_retry, "_installed", False)
    monkeypatch.setattr(dns_retry.time, "sleep", lambda seconds: None)

    dns_retry.install()
    dns_retry.install()

    assert socket.getaddrinfo("wiki.home.example", 443) == ["wiki.home.example:443"]
    assert len(calls) == 2  # wrapped exactly once: one retry, not nested retries
