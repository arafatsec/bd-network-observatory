# Probe v0: connectivity logger

v0 is a prototype of the local connectivity logger described in the [README](../README.md). It runs on one machine, checks the network at fixed intervals, and records **which layer fails** (DNS, TCP or HTTP) to local files. It keeps recording during a full blackout, because it needs no network to write.

## What v0 is not

- **Not OONI Probe.** It does not run OONI's blocking tests and sends nothing to OONI. OONI integration comes later.
- **Not uploading anything.** All data stays in the local `data/` folder. The store-and-forward uploader is a stub that does nothing (`probe/uploader.py`).
- **Not deployed.** No probes are running on any network yet.
- **Not measuring everything in the plan.** v0 does not measure routing or throughput, and it does not record the network's ASN or region.

## How it works

Every cycle (default 60 s) runs these checks in parallel, each with a 4-second timeout:

| Layer | Checks |
|---|---|
| DNS | `example.com`, `wikipedia.org` and `cloudflare.com` (A records), each through `1.1.1.1`, `8.8.8.8` and `9.9.9.9` (dnspython) and through the system resolver: 12 lookups in total |
| TCP | Connect to `1.1.1.1:443`, `8.8.8.8:443` and `9.9.9.9:443`, recording the connect time |
| HTTP | `GET https://cp.cloudflare.com/generate_204` and `https://www.google.com/generate_204` |

A layer counts as **up** if at least one of its targets succeeds. An HTTP check succeeds only on status **204**. Redirects are not followed, and the system proxy is ignored, so a captive portal or block page shows up as a failure with its status code.

Each cycle gets one classification. Failures are checked from the lowest layer up, because higher layers depend on lower ones:

| Classification | Meaning |
|---|---|
| `offline` | Every check failed |
| `dns_fail` | No DNS lookup succeeded |
| `tcp_fail` | DNS works, but no TCP connection succeeded |
| `http_fail` | DNS and TCP work, but no HTTP check returned 204 |
| `degraded` | Every layer works, but the median TCP connect time is well above the baseline: more than 3× the baseline **and** more than 100 ms above it |
| `ok` | Every layer works at normal latency |

The **baseline** is the median TCP connect time of the last 30 `ok` cycles. Slow or failed cycles never update it, so a long slow period cannot become the new normal. This is deliberate: sustained slowness is exactly what throttling looks like, so it keeps being reported as `degraded` rather than being absorbed. The baseline starts empty each time the probe starts, so the first 5 `ok` cycles cannot be marked `degraded`. Only TCP connect time is used for latency; slow DNS or HTTP alone does not make a cycle `degraded`.

A check that has not finished by the cycle deadline (timeout + 1 s) is recorded as failed with the error `CycleDeadlineExceeded`. A check that fails in an unexpected way is recorded as failed with the error type, and the probe keeps running.

The rules are in `probe/classify.py`, a pure function with no network access.

## Running it

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m probe run                    # every 60 s until Ctrl+C
python -m probe run --interval 120     # any interval of 15 s or more
python -m probe summary --date 2026-10-03
python -m probe dashboard --date 2026-10-10 --days 7
```

Intervals under 15 s are refused, because they add load to the test servers without adding much information. Each cycle prints a single status line (time, classification, latency). Ctrl+C stops the probe, and every completed cycle has already been saved.

`summary` reads one UTC day and lists **outage periods**: consecutive non-`ok` cycles with the same classification. A period starts at its first failing cycle and ends at the first cycle that shows a different state, so start and end are accurate to within one interval. A duration ending in `+` means the outage was still going when the log ended. Gaps longer than three intervals are listed as `no_data`: the probe was not running, which is different from an outage. An outage that crosses midnight UTC appears in both days' summaries.

### Dashboard

`dashboard` turns the logs for one or more UTC days (`--days`, up to 31, ending at `--date`, default today) into a single HTML page, written to `data/dashboard-FIRST_LAST.html` unless `--out` says otherwise. It shows:

- headline numbers: cycles recorded, share fully ok, outages and their total time, slowdowns, median latency, and data coverage (how much of the time span has records)
- a timeline with the status of every cycle, where gaps appear as `no data`
- TCP connect latency over time against the rolling baseline
- success rate and median time for each resolver, TCP target and HTTP URL
- every outage, slowdown and gap, as in `summary` but across days, so outages crossing midnight stay in one piece

The page is self-contained: inline SVG charts, no JavaScript, nothing loaded from the internet. It opens offline in any browser, works on phones, and follows the system's light or dark mode. It contains only what the logs contain, so it is written into the gitignored `data/` folder by default.

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests never use the network: every check is mocked, and a fixture fails any test that opens a socket.

## Storage

Each cycle appends one JSON object as a single line to `data/YYYY-MM-DD.jsonl`, named by UTC date. Every write is flushed and `fsync`ed before the next cycle, so a power cut loses at most the cycle being written. If a write is cut off halfway, the next write starts on a fresh line, and the reader skips (and counts) the broken line. `data/` is gitignored.

If a write fails (for example a full disk or a file locked by antivirus), the probe prints a warning, loses that one cycle, and keeps measuring.

Each record is about 2 KB, so at the default 60 s interval a day's log is about 3 MB.

## What is recorded

Each record contains only:

- `v` (schema version), `ts` (cycle start, ISO-8601 UTC), `interval_s`
- `classification`, `latency_ms` (median TCP connect time) and `baseline_ms`
- For every DNS check: the resolver (one of the three public addresses, or the word `system`), the name, success, time, the addresses returned for that public name, and the error type
- For every TCP check: the target, success, connect time and error type
- For every HTTP check: the URL, success, status code, time and error type

Example (shortened):

```json
{"v":1,"ts":"2026-10-03T04:46:12Z","interval_s":15,"classification":"ok","latency_ms":38.5,"baseline_ms":null,
 "dns":[{"resolver":"1.1.1.1","name":"example.com","ok":true,"ms":41.2,"answers":["..."],"error":null}, ...],
 "tcp":[{"target":"1.1.1.1:443","ok":true,"ms":38.5,"error":null}, ...],
 "http":[{"url":"https://cp.cloudflare.com/generate_204","ok":true,"status":204,"ms":120.4,"error":null}, ...]}
```

## What is deliberately not recorded

In line with [ETHICS.md](ETHICS.md), the probe never collects, so never stores:

- the machine's public or local IP address
- the system resolver's address (often a home router or ISP address); it is recorded only as `system`
- private, link-local or other non-public addresses in DNS answers: if a router or captive portal answers with its own address (such as `192.168.1.1`), it is recorded as `non-public`. `0.0.0.0` and `127.0.0.1` are kept, because they are common DNS-blocking responses and say nothing about the host.
- the hostname, username, Wi-Fi network name or any location
- response bodies, headers or anyone's traffic

Errors are stored as the exception **type** only (for example `TimeoutError`), never the message, because messages can include local addresses or file paths.

## Known limitations

- The HTTP targets belong to Cloudflare and Google. If only those were blocked, the cycle would show as `http_fail` even though other sites work. Telling these cases apart is OONI Probe's job.
- Outage start and end times are accurate to within one interval.
- The baseline resets when the probe restarts.
- A single machine cannot tell a local fault (unplugged cable, router reboot) from a network-wide shutdown. That needs many probes across operators, which is the purpose of the full project.
