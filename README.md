# Bangladesh Network Interference Observatory

Independent, continuous measurement of internet shutdowns, throttling and platform blocking in Bangladesh, including **during** full blackouts.

> **Status: early prototype.** A v0 connectivity logger exists and runs on a single machine, logging locally. It does not run OONI Probe or upload anything yet, and no probes are deployed. This repository holds the plan and the probe software as it is built.

## Why

In July–August 2024 Bangladesh went through the longest and most widespread internet shutdown in its history, including a nationwide blackout from 18 to 23 July 2024. The most complete record of it, [*The Longest Silence*](https://ooni.org/documents/2025-bd-report-en.pdf) by OONI and Digitally Right (July 2025), notes that measurement coverage varied across networks and over time, and that measurement stopped entirely during full blackouts.

Bangladesh's Telecommunication Ordinance 2025 states that internet services cannot be suspended. A promise like that is only as strong as the ability to check it independently. Quieter controls, such as regional throttling, single-platform blocks or DNS tampering, are easy to deny without continuous measurement from inside the networks.

## What this project does

- **Blackout-resilient probes.** Small Linux probes run [OONI Probe](https://ooni.org/install/) for blocking tests and also log connectivity locally (DNS, routing, latency, throughput). During a blackout they keep recording which layer failed, and upload when service returns.
- **Operator-wide coverage.** About 30 probes across Grameenphone, Robi, Banglalink, Teletalk and major broadband ISPs, in all eight divisions.
- **Complement, not compete.** All blocking tests run on OONI Probe, so results flow into OONI's open dataset. This project adds coverage and blackout evidence that OONI and outside-in monitors such as IODA cannot collect today.
- **Open output.** Alerts for journalists and digital rights groups when anomalies appear, a public dashboard, and reports in English and Bangla.

## Plan (12 months)

1. **Months 1–2:** ethics and safety plan, volunteer consent process, coordination with OONI and Digitally Right.
2. **Months 2–4:** build the store-and-forward probe in Python and test it on one unit.
3. **Months 3–6:** deploy about 30 probes: 20 on mobile networks (5 per operator) and 10 on broadband.
4. **Months 4–12:** continuous measurement, per-operator throttling baselines, automated alerts.
5. **Months 6 and 12:** public reports and dashboard.

## Hardware (planned)

Raspberry Pi Zero 2 W, 64 GB microSD and power adapter per probe; mobile probes add a USB LTE modem. A single unit will be tested with OONI Probe before any wider purchase, because the Zero 2 W has 512 MB of memory.

## Run the prototype

The v0 logger checks DNS, TCP and HTTP at fixed intervals and records which layer fails, to local files only. It needs Python 3.11+ and works on Windows and Linux:

```bash
pip install -r requirements.txt
python -m probe run --interval 60
python -m probe summary --date YYYY-MM-DD
python -m probe dashboard --date YYYY-MM-DD --days 7   # HTML dashboard, opens offline
```

See [docs/PROBE.md](docs/PROBE.md) for how it works, what it records and what it deliberately does not record.

## Safety and ethics

See [docs/ETHICS.md](docs/ETHICS.md). In short: informed consent from every probe host, no probe on any network without its owner's permission, and no collection of personal data.

## Licence

Code and documentation are released under the [MIT Licence](LICENSE). Measurement data will be published under an open data licence.

## Contact

Arafat Ul Islam, Dhaka, Bangladesh · arafat86814@gmail.com
