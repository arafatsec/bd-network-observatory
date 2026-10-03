import threading
import urllib.error

import dns.exception
import dns.resolver

from probe import checks
from probe.checks import DEADLINE_ERROR, CheckResults, DnsResult, HttpResult, TcpResult


class FakeContext:
    def __init__(self, status=None):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_tcp_success_records_time(monkeypatch):
    monkeypatch.setattr(checks.socket, "create_connection", lambda addr, timeout: FakeContext())
    result = checks.check_tcp("1.1.1.1", 443, 1.0)
    assert result.ok and result.ms is not None and result.target == "1.1.1.1:443"


def test_tcp_failure_records_error_type_only(monkeypatch):
    def refuse(addr, timeout):
        raise ConnectionRefusedError("message text that could include local details")

    monkeypatch.setattr(checks.socket, "create_connection", refuse)
    result = checks.check_tcp("1.1.1.1", 443, 1.0)
    assert (result.ok, result.ms, result.error) == (False, None, "ConnectionRefusedError")


def test_dns_via_resolver_failure(monkeypatch):
    def timeout(self, name, rdtype):
        raise dns.exception.Timeout()

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", timeout)
    result = checks.check_dns_via("8.8.8.8", "example.com", 1.0)
    assert (result.ok, result.resolver, result.error, result.answers) == (False, "8.8.8.8", "Timeout", ())


def test_dns_via_resolver_success(monkeypatch):
    class Rec:
        def __init__(self, address):
            self.address = address

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", lambda self, name, rdtype: [Rec("2.2.2.2"), Rec("1.1.1.1")])
    result = checks.check_dns_via("1.1.1.1", "example.com", 1.0)
    assert result.ok and result.answers == ("1.1.1.1", "2.2.2.2")


def test_system_dns_is_labelled_not_addressed(monkeypatch):
    monkeypatch.setattr(checks.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.215.14", 443))] * 2)
    result = checks.check_dns_system("example.com", 1.0)
    assert result.resolver == "system"
    assert result.answers == ("93.184.215.14",)


def test_http_204_is_ok(monkeypatch):
    monkeypatch.setattr(checks._OPENER, "open", lambda req, timeout: FakeContext(204))
    result = checks.check_http("https://example.test/generate_204", 1.0)
    assert result.ok and result.status == 204


def test_http_200_is_not_ok(monkeypatch):
    # A 200 where a 204 is expected usually means a captive portal or block page.
    monkeypatch.setattr(checks._OPENER, "open", lambda req, timeout: FakeContext(200))
    result = checks.check_http("https://example.test/generate_204", 1.0)
    assert not result.ok and result.status == 200 and result.error is None


def test_http_redirect_is_recorded_not_followed(monkeypatch):
    def redirect(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 302, "Found", {}, None)

    monkeypatch.setattr(checks._OPENER, "open", redirect)
    result = checks.check_http("https://example.test/generate_204", 1.0)
    assert not result.ok and result.status == 302


def test_http_network_error_uses_underlying_type(monkeypatch):
    def fail(req, timeout):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(checks._OPENER, "open", fail)
    result = checks.check_http("https://example.test/generate_204", 1.0)
    assert (result.ok, result.status, result.error) == (False, None, "TimeoutError")


def fake_ok_checks():
    return {
        "dns_via": lambda r, n, t: DnsResult(r, n, True, 1.0, (), None),
        "dns_system": lambda n, t: DnsResult("system", n, True, 1.0, (), None),
        "tcp": lambda h, p, t: TcpResult(f"{h}:{p}", True, 1.0, None),
        "http": lambda u, t: HttpResult(u, True, 204, 1.0, None),
    }


def test_run_checks_covers_every_target():
    results = checks.run_checks(1.0, **fake_ok_checks())
    assert isinstance(results, CheckResults)
    assert len(results.dns) == 12 and len(results.tcp) == 3 and len(results.http) == 2
    assert all(r.ok for r in (*results.dns, *results.tcp, *results.http))


def test_hung_check_is_reported_at_the_deadline():
    release = threading.Event()

    def hangs(name, timeout):
        release.wait(5)
        return DnsResult("system", name, True, 1.0, (), None)

    try:
        results = checks.run_checks(0.05, **{**fake_ok_checks(), "dns_system": hangs})
    finally:
        release.set()
    system = [r for r in results.dns if r.resolver == "system"]
    assert len(system) == 3
    assert all(r.error == DEADLINE_ERROR and not r.ok for r in system)
    assert all(r.ok for r in results.tcp)


def test_private_dns_answers_are_redacted():
    answers = checks.safe_answers(
        ["93.184.215.14", "192.168.1.1", "10.0.0.5", "172.16.0.1", "100.64.0.1", "169.254.1.1",
         "fe80::1%eth0", "fd00::1", "2606:4700::1111", "not-an-ip"]
    )
    assert answers == ("2606:4700::1111", "93.184.215.14", checks.NON_PUBLIC_ANSWER)


def test_blocking_style_answers_are_kept():
    # 0.0.0.0 and loopback are classic DNS-blocking responses and reveal nothing about the host.
    assert checks.safe_answers(["0.0.0.0", "127.0.0.1", "::"]) == ("0.0.0.0", "127.0.0.1", "::")


def test_system_dns_redacts_router_address(monkeypatch):
    monkeypatch.setattr(checks.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.0.1", 443))])
    result = checks.check_dns_system("example.com", 1.0)
    assert result.ok and result.answers == (checks.NON_PUBLIC_ANSWER,)


def test_unexpected_exception_in_a_check_is_recorded_not_raised():
    def broken(host, port, timeout):
        raise UnicodeError("unexpected")

    results = checks.run_checks(1.0, **{**fake_ok_checks(), "tcp": broken})
    assert all((r.ok, r.error) == (False, "UnicodeError") for r in results.tcp)
    assert all(r.ok for r in results.dns)


def test_hung_check_thread_is_a_daemon():
    # A daemon thread cannot keep the process alive after Ctrl+C.
    release = threading.Event()
    seen: list[bool] = []

    def hangs(name, timeout):
        seen.append(threading.current_thread().daemon)
        release.wait(5)
        return DnsResult("system", name, True, 1.0, (), None)

    try:
        checks.run_checks(0.05, **{**fake_ok_checks(), "dns_system": hangs})
    finally:
        release.set()
    assert seen and all(seen)
