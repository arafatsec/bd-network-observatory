import socket

import pytest

from probe.checks import CheckResults, DnsResult, HttpResult, TcpResult


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test tries to reach the real network."""

    def blocked(*args, **kwargs):
        raise AssertionError("tests must not use the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)


def make_results(*, dns_ok=True, tcp_ok=True, http_ok=True, tcp_ms=20.0) -> CheckResults:
    """A fake cycle where each layer is entirely up or entirely down."""
    dns = (
        DnsResult("1.1.1.1", "example.com", dns_ok, 10.0 if dns_ok else None,
                  ("93.184.215.14",) if dns_ok else (), None if dns_ok else "Timeout"),
        DnsResult("system", "example.com", dns_ok, 5.0 if dns_ok else None,
                  ("93.184.215.14",) if dns_ok else (), None if dns_ok else "gaierror"),
    )
    tcp = tuple(
        TcpResult(f"{ip}:443", tcp_ok, tcp_ms if tcp_ok else None, None if tcp_ok else "TimeoutError")
        for ip in ("1.1.1.1", "8.8.8.8", "9.9.9.9")
    )
    http = (
        HttpResult("https://cp.cloudflare.com/generate_204", http_ok, 204 if http_ok else None,
                   50.0 if http_ok else None, None if http_ok else "TimeoutError"),
    )
    return CheckResults(dns=dns, tcp=tcp, http=http)
