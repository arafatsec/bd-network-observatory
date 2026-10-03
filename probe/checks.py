"""Network checks for one measurement cycle.

Each check returns a result object instead of raising, so one failing layer never
stops the others from being measured. Errors are recorded by exception type name
only: exception messages can contain local addresses or paths.
"""

import http.client
import ipaddress
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable

import dns.exception
import dns.resolver

from probe import targets


@dataclass(frozen=True)
class DnsResult:
    resolver: str
    name: str
    ok: bool
    ms: float | None
    answers: tuple[str, ...]
    error: str | None


@dataclass(frozen=True)
class TcpResult:
    target: str
    ok: bool
    ms: float | None
    error: str | None


@dataclass(frozen=True)
class HttpResult:
    url: str
    ok: bool
    status: int | None
    ms: float | None
    error: str | None


@dataclass(frozen=True)
class CheckResults:
    dns: tuple[DnsResult, ...]
    tcp: tuple[TcpResult, ...]
    http: tuple[HttpResult, ...]


# Reported when a check has not returned by the cycle deadline (e.g. a system
# resolver call that ignores timeouts).
DEADLINE_ERROR = "CycleDeadlineExceeded"

# Replaces DNS answers in private, link-local, CGNAT or other non-public ranges.
# A router or captive portal answering with its own address (e.g. 192.168.1.1)
# would otherwise reveal the host's local network.
NON_PUBLIC_ANSWER = "non-public"


def safe_answers(addresses) -> tuple[str, ...]:
    """Keep public addresses, plus 0.0.0.0 and loopback, which are common DNS
    blocking responses and reveal nothing about the host."""
    kept = set()
    for address in addresses:
        try:
            ip = ipaddress.ip_address(str(address).split("%", 1)[0])
        except ValueError:
            kept.add(NON_PUBLIC_ANSWER)
            continue
        kept.add(str(ip) if ip.is_global or ip.is_unspecified or ip.is_loopback else NON_PUBLIC_ANSWER)
    return tuple(sorted(kept))


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _error_name(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
        return type(exc.reason).__name__
    return type(exc).__name__


def check_dns_via(resolver_ip: str, name: str, timeout: float) -> DnsResult:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_ip]
    resolver.timeout = timeout
    resolver.lifetime = timeout
    start = time.perf_counter()
    try:
        answer = resolver.resolve(name, "A")
    except (dns.exception.DNSException, OSError) as exc:
        return DnsResult(resolver_ip, name, False, None, (), _error_name(exc))
    answers = safe_answers(record.address for record in answer)
    return DnsResult(resolver_ip, name, True, _elapsed_ms(start), answers, None)


def check_dns_system(name: str, timeout: float) -> DnsResult:
    # getaddrinfo has no timeout of its own; run_checks enforces the deadline.
    del timeout
    start = time.perf_counter()
    try:
        infos = socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return DnsResult(targets.SYSTEM_RESOLVER, name, False, None, (), _error_name(exc))
    answers = safe_answers(info[4][0] for info in infos)
    return DnsResult(targets.SYSTEM_RESOLVER, name, True, _elapsed_ms(start), answers, None)


def check_tcp(host: str, port: int, timeout: float) -> TcpResult:
    target = f"{host}:{port}"
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return TcpResult(target, False, None, _error_name(exc))
    return TcpResult(target, True, _elapsed_ms(start), None)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report redirects as-is: a redirect from a generate_204 URL is itself a signal
    (captive portal or block page), so it must not be followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


# Empty ProxyHandler: measure the direct path, not whatever proxy the OS is set to.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def check_http(url: str, timeout: float) -> HttpResult:
    request = urllib.request.Request(url, headers={"User-Agent": targets.USER_AGENT})
    start = time.perf_counter()
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        return HttpResult(url, False, None, None, _error_name(exc))
    return HttpResult(url, status == 204, status, _elapsed_ms(start), None)


def run_checks(
    timeout: float = targets.CHECK_TIMEOUT_S,
    *,
    dns_via: Callable[[str, str, float], DnsResult] = check_dns_via,
    dns_system: Callable[[str, float], DnsResult] = check_dns_system,
    tcp: Callable[[str, int, float], TcpResult] = check_tcp,
    http: Callable[[str, float], HttpResult] = check_http,
) -> CheckResults:
    """Run every check in parallel and return within about timeout + 1 seconds."""
    dns_jobs: list[Job] = []
    for resolver in (*targets.PUBLIC_RESOLVERS, targets.SYSTEM_RESOLVER):
        for name in targets.DNS_NAMES:
            fallback = DnsResult(resolver, name, False, None, (), DEADLINE_ERROR)
            if resolver == targets.SYSTEM_RESOLVER:
                dns_jobs.append(Job(lambda n=name: dns_system(n, timeout), fallback))
            else:
                dns_jobs.append(Job(lambda r=resolver, n=name: dns_via(r, n, timeout), fallback))
    tcp_jobs = [
        Job(lambda h=host, p=port: tcp(h, p, timeout), TcpResult(f"{host}:{port}", False, None, DEADLINE_ERROR))
        for host, port in targets.TCP_TARGETS
    ]
    http_jobs = [
        Job(lambda u=url: http(u, timeout), HttpResult(url, False, None, None, DEADLINE_ERROR))
        for url in targets.HTTP_URLS
    ]

    results = run_parallel([*dns_jobs, *tcp_jobs, *http_jobs], deadline_s=timeout + 1.0)
    dns_end = len(dns_jobs)
    tcp_end = dns_end + len(tcp_jobs)
    return CheckResults(
        dns=tuple(results[:dns_end]),
        tcp=tuple(results[dns_end:tcp_end]),
        http=tuple(results[tcp_end:]),
    )


@dataclass(frozen=True)
class Job:
    run: Callable[[], object]
    # Returned if the check misses the deadline; also the template for crashes.
    fallback: object


def run_parallel(jobs: list[Job], deadline_s: float) -> list:
    """Run jobs on daemon threads and return whatever finished by the deadline.

    Daemon threads (not a thread pool) so a hung system resolver call can never
    stop the process from exiting on Ctrl+C. A check that raises unexpectedly is
    recorded as a failure with the exception type, so one bug cannot stop the
    logger during the very blackout it exists to record.
    """
    slots = [job.fallback for job in jobs]

    def work(index: int, job: Job) -> None:
        try:
            slots[index] = job.run()
        except Exception as exc:  # recorded in the result, not hidden
            slots[index] = replace(job.fallback, error=type(exc).__name__)

    threads = [
        threading.Thread(target=work, args=(i, job), name=f"probe-check-{i}", daemon=True)
        for i, job in enumerate(jobs)
    ]
    for thread in threads:
        thread.start()
    give_up_at = time.monotonic() + deadline_s
    for thread in threads:
        thread.join(max(0.0, give_up_at - time.monotonic()))
    # Snapshot: a check finishing after the deadline cannot change this cycle.
    return list(slots)
