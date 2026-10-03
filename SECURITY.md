# Security policy

## Reporting a vulnerability

Please report security problems **privately** by email to **arafat86814@gmail.com**.

**Do not open a public GitHub issue** for a security problem. Probes may run on volunteers' connections, so a public report could put people at risk before a fix is available.

Please include:

- what you found and where (file, commit, or component)
- how to reproduce it
- what an attacker could do with it, as far as you know

I will acknowledge your report as soon as I can. Please allow reasonable time for a fix before disclosing the problem publicly.

## Scope

Of particular interest:

- anything that could make a probe record or send data that identifies its host (IP address, hostname, username, Wi-Fi name, location), contrary to [docs/ETHICS.md](docs/ETHICS.md)
- anything that lets a third party alter or read a probe's local logs, or run code on the probe
- weaknesses in the future upload path, once it exists

The probe is currently a v0 prototype and is not deployed anywhere.
