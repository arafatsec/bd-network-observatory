# Information sheet and consent form for probe hosts

> **Status: draft for review** (see [SAFETY-PLAN.md](SAFETY-PLAN.md), section 8). A Bangla version must be prepared and checked by a native speaker before use. Hosts may choose either language; if the two differ, the version the host signed applies.

Hosts receive this sheet **at least three days** before a probe is installed, and are encouraged to ask questions before signing.

---

## Part 1: Information sheet

### What is this project?

The Bangladesh Network Interference Observatory measures internet shutdowns, slowdowns and website blocking in Bangladesh, independently and continuously, including during full blackouts. The results help journalists, researchers and digital rights groups know what actually happened to the internet, and when.

### What would the probe do on my connection?

A probe is a small device (or a program on a computer) that, about once a minute:

- looks up a few well-known website names (such as `example.com` and `wikipedia.org`) using public DNS services
- opens a connection to three public internet addresses
- requests two small test pages from Cloudflare and Google

and writes down whether each step worked and how long it took. Later, it will also run [OONI Probe](https://ooni.org/install/) tests, which check whether specific websites and apps are blocked.

### What does it NOT do?

- It does **not** look at, record or send anything you or anyone else does on the internet.
- It does **not** record your IP address, your name, your Wi-Fi name, your location, or anything about your devices.
- It uses very little data: about 3 MB of logs per day, and the test traffic itself is small. Mobile probes use their own SIM card provided by the project, so they never use your mobile data.

### Who sees the results?

Results are published openly, identified only by **network** (for example "Grameenphone") and **division** (for example "Khulna"). Nobody outside the project's core team is told who hosts which probe. Where you could be the only host on your network in your division, results are published in a more general way until there are more hosts.

### What are the risks?

Measuring internet censorship is widely done around the world, for example through OONI, and does not involve looking at anyone's private data. Before any probe is installed with a host, the project has the legal situation in Bangladesh reviewed by a lawyer. Even so, this work can attract attention, and political conditions can change. The main risk is that someone could learn that you host a probe and pressure you about it. The project reduces this risk by never publishing who you are, never registering probe SIM cards in your name, and pausing the network if the situation becomes dangerous (see the safety plan). We cannot promise there is no risk at all.

### Can I stop?

**Yes, at any time, without giving a reason.** Contact the project (details below). We will stop the probe remotely, usually within 24 hours, arrange to collect it or let you switch it off, and delete its raw data that has not yet been published if you ask. Results that are already published, which never mention you, cannot be withdrawn.

### Other people on my connection

If others share your connection (family, flatmates, colleagues), please tell them about the probe. It never sees their traffic, but they should know it is there.

### Contact

Project lead: Arafat Ul Islam, arafat86814@gmail.com

---

## Part 2: Consent form

*Kept by the project lead, encrypted and separate from all measurement data. Never published.*

Please tick each box only if it is true.

- [ ] I am 18 or older.
- [ ] I have read the information sheet (or had it read to me) in a language I understand, and my questions have been answered.
- [ ] I control this internet connection, **or** I have written permission from the person or organisation that does. *(Attach or describe the permission:)* ________________________________
- [ ] I understand what the probe does and does not do.
- [ ] I understand the risks described, including that no risk can be ruled out completely.
- [ ] I understand that results will be published by network and division, and that the project will not publish who I am.
- [ ] I understand that I can withdraw at any time without giving a reason.
- [ ] I agree to the project contacting me every six months, and in emergencies, to re-confirm or pause.
- [ ] I will tell people who share this connection that a probe is installed.

Preferred way to contact me (not stored with measurement data): ________________________________

Host name: ________________________________ Signature: ________________ Date: ____________

Project representative: ________________________________ Signature: ________________ Date: ____________

*If consent is given verbally, the project representative records here: date, time, language used, and who was present:* ________________________________
