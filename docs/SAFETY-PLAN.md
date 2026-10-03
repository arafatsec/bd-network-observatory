# Safety plan

> **Status: draft for review.** This plan has not yet been reviewed by a lawyer or by the independent reviewers named in [ETHICS.md](ETHICS.md). Points marked **[legal check]** depend on current Bangladeshi law and must be confirmed before any probe is placed with a host. Nothing here is legal advice.

This plan turns the rules in [ETHICS.md](ETHICS.md) into concrete steps. It covers who could be harmed, how hosts are chosen and asked for consent, how data is handled, how probes are secured, how SIM cards are handled, and what happens when something goes wrong.

## 1. Who could be harmed, and how

| Who | Possible harm | Likelihood today | Main protections |
|---|---|---|---|
| **Probe hosts** (people or institutions whose connection a probe uses) | Being identified as part of a censorship-measurement project; questioned or pressured if political conditions change | Low now, could rise quickly during unrest | Host anonymity in all published data (section 4), informed consent with the right to withdraw (section 3), pause procedure (section 7) |
| **Hosts' households or colleagues** | Same as above, without having agreed to anything | Low | Probes measure only public test servers and never see other people's traffic; hosts are told to inform people who share the connection |
| **SIM-card holders** | A SIM registered to someone's national ID links that person to the probe | Low to medium | SIMs are never registered to hosts (section 6) |
| **Project staff and volunteers** | Legal or personal pressure as the visible face of the project | Low to medium | Public communication from the project, not individuals; legal contact arranged in advance (section 7) |
| **Network owners** (ISPs, institutions) | Breach of their terms of service or internal rules | Low | Written owner permission for every non-home connection (section 2) |

The likelihood column reflects conditions at the time of writing. It must be re-assessed before each deployment phase and whenever political conditions change sharply (section 7).

## 2. Choosing hosts

A probe is placed only with a host who meets **all** of these:

1. **Adult** (18 or over) and able to give informed consent.
2. **Controls the connection**, or has **written permission** from whoever does. For institutional, office or shared connections (universities, companies, co-working spaces) that means written permission from the person responsible for the network. A tenant on a landlord's line needs the landlord's agreement if the contract requires it **[legal check]**.
3. **Not in a role that raises their risk**: for example, not a journalist, activist or government employee who could face extra scrutiny for being linked to the project, unless they explicitly understand and accept that higher risk.
4. **Has someone to contact**: they know who to call in the project, and the project can reach them, without that contact information ever entering measurement data.

Host selection aims for coverage across operators and all eight divisions (see the README plan), but **safety comes before coverage**. A region without a suitable host stays uncovered.

## 3. Consent

Consent is a process, not a one-time signature.

1. **Information first.** The host receives the information sheet in [CONSENT.md](CONSENT.md), in Bangla or English as they prefer, at least **three days** before installation, and can ask questions.
2. **Written consent.** The host signs (or records a clear verbal consent, noted by the project) only after their questions are answered. Consent records are kept by the project lead, encrypted and **separate from all measurement data**. They are never published.
3. **Withdrawal at any time.** The host can withdraw by message or call, without giving a reason. The project then stops the probe remotely within 24 hours where possible, collects or the host keeps the device as agreed, and deletes that probe's unpublished raw data on request (published aggregates cannot be recalled; the information sheet says so).
4. **Re-confirmation.** Consent is re-confirmed **every six months**, and immediately after any event that changes the risk (section 7).

## 4. Data handling

**Collected** (see [PROBE.md](PROBE.md) for the exact record format): timestamps, the fixed test targets, success or failure, timings, status codes, and the addresses that public test names resolve to.

**Never collected:** the host's IP address, hostname, username, Wi-Fi name, location, or any traffic other than the probe's own test connections. The v0 software enforces this in code and in its tests, including replacing private or router addresses in DNS answers with `non-public`.

| Data | Where it lives | Who can access it | Kept for |
|---|---|---|---|
| Raw probe logs | On the probe; later on a project server (store-and-forward, not built yet) | Project lead and named technical team | Until published in aggregate, then **at most 12 months**, then deleted |
| Published results | OONI's open dataset (blocking tests); project reports and dashboard (connectivity) | Everyone | Permanently (public record) |
| Probe-to-host mapping (which probe is at which host) | Encrypted, offline, held by the project lead only | Project lead only | While the probe is deployed, then deleted |
| Consent records and host contact details | Encrypted, separate from all data | Project lead only | While the probe is deployed plus 12 months, then deleted |

**Publication rules:**

- A probe is identified publicly only by **network (ASN) and division**. In a division with only one probe on a given network, results are published at a coarser level (for example "mobile networks, Rangpur division") until there are at least two probes, so no single host can be pointed out.
- Timing details that could reveal a host's routine (for example when their power or router goes off every night) are aggregated before publication.

**The future uploader** (Milestone 2) must send data only over an encrypted connection, to a server the project controls, carrying no more fields than this plan allows, and must survive interception without revealing the host. It needs its own short design review against this section before it is enabled.

## 5. Probe device security

- **Single purpose.** Probes run only the probe software (and OONI Probe once integrated). No other services, shared folders, or user accounts.
- **Remote access** only with keys, never passwords, and only over an encrypted private network; never open to the internet or the host's local network. (The test PC used in the pilot follows this already: SSH and Remote Desktop accept connections only through the project's private Tailscale network.)
- **Updates** are applied by the project, not the host, at planned times recorded so they are not mistaken for network events.
- **Physical loss.** Storage holds only measurement data, which contains nothing about the host by design. Remote-access keys for a lost or seized device are revoked immediately.
- **Labelling.** Devices carry a neutral label with the project contact, not a description such as "censorship monitor" **[legal check: whether a fuller label is required or advisable]**.

## 6. SIM cards

Mobile probes need SIM cards, and every Bangladeshi SIM is registered against a person's national ID **[legal check: current registration rules and limits]**. The SIM must never point to the host.

| Option | How | Risk to hosts | Risk to the project | Assessment |
|---|---|---|---|---|
| **A. Organisation-registered SIMs** | A partner organisation registers SIMs in its own name | None | Low; the organisation is the visible owner | **Preferred**, if a partner (for example Digitally Right) agrees and the operator allows corporate registration **[legal check]** |
| **B. Project-lead-registered SIMs** | The project lead registers SIMs to their own ID | None | Concentrates risk on one person; per-ID SIM limits may cap the number of probes **[legal check]** | **Fallback** if option A is not possible |
| **C. Host's own SIM** | The probe uses a SIM the host already owns | **High**: links the host to the probe in operator records | Low | **Not allowed** |

Whatever option is used, the SIM-to-probe mapping is stored with the probe-to-host mapping (section 4) and treated the same way.

## 7. When something goes wrong

**Triggers** that start this procedure:

- a nationwide or regional shutdown, curfew, or state of emergency
- any contact from authorities, an ISP, or a network owner about a probe
- a probe device lost, stolen, or seized
- credible reports that measurement projects or their participants are being targeted
- a host asking to stop

**Actions:**

1. **Pause.** Probes keep logging locally (that is their purpose during blackouts) but **uploads and public alerts pause** until the project lead reviews the situation, unless all hosts in the affected area have agreed in advance to continued publication.
2. **Contact hosts** in the affected area through the agreed channel. Offer to remove the probe or withdraw.
3. **Revoke** access for any lost or seized device.
4. **Get advice** from the legal contact arranged in advance (to be named before the first host deployment).
5. **Record** what happened and what was done, without host-identifying details, for the review in section 8.

## 8. Review and sign-off

Before the first probe is placed with **any host other than the project lead**:

- [ ] This plan reviewed by a lawyer familiar with current Bangladeshi telecom and cyber law (all **[legal check]** points closed)
- [ ] Independent security and ethics review completed, as required by [ETHICS.md](ETHICS.md)
- [ ] OONI and Digitally Right consulted on the plan (README, Milestone 1)
- [ ] SIM option decided (section 6)
- [ ] Legal contact for incidents named (section 7)
- [ ] Bangla version of the information sheet and consent form checked by a native speaker

**Pilot on the project lead's own equipment.** A one-week test of the v0 logger runs (October 2026) on a test PC that the project lead administers, on a network whose use the project lead has authorised. It involves no third-party host, collects only the data listed in section 4, and uploads nothing. Its results are described as coming from **one institutional wired network**, not a household connection.

## 9. Open questions for the review

1. Which partner, if any, can hold organisation-registered SIMs (option 6A)?
2. Does any current law require registration or notification for network measurement, or limit publishing outage data? **[legal check]**
3. Is division-level publication coarse enough in sparsely covered divisions, or should some results be national-level only?
4. Should hosts be offered a small compensation for electricity and connectivity, and does that change the consent or legal picture?
5. Who besides the project lead should be able to pause the network in an emergency, so that the plan does not depend on one person?
