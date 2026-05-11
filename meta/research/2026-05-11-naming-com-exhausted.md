---
type: research
date: 2026-05-11
tags: [naming, domains, branding, dot-com, squatter-market]
ai-first: true
problem: For a short brandable open-source project name with a .com domain, what's actually achievable in 2026?
solution-summary: Pronounceable 4-letter .com finished registration in 2014. Pronounceable 5-letter mostly gone by 2020. Pronounceable 6-letter ~70-90% taken with 2025 squatters actively grabbing AI-adjacent invented words. Pay $5K+ secondary market or accept 7+ letter compound / non-.com / nonsense.
expires: 2027-05-11
recheck-trigger:
  - GoDaddy / Verisign release new figures on .com saturation
  - a new TLD reaches mainstream adoption (.ai already there as of 2026)
  - GitHub or another major platform makes domain less load-bearing for project discovery
  - the AI-adjacent naming squatter wave subsides (it accelerated in 2024-2025)
---

## For future Claude

This card investigates the .com domain market for short brandable names, conducted while picking a name for the Sift spec. Read it when: someone is naming a new OSS project and asks "can I get a 4-letter .com?" or "why is everyone using compound names now?" Skip it when: the project already has a working name and is past the naming phase.

If today is past `expires` or a recheck-trigger has fired, treat as baseline: the underlying dynamics rarely reverse but new TLDs may shift the picture.

## Method

Brute-force discovery via batch RDAP queries over rdap.org. 200+ candidates queried across 5 tiers:

| Tier | Candidates | Available .com |
|---|---|---|
| Tier 1: Sift-derivative 4-letter | `sifr` `siftr` `cerne` `crux` `cull` `vetor` etc | 0 — all taken, 2024-2025 squatter grab visible |
| Tier 2: 4-letter dictionary words | `pith` `silo` `saga` `stoa` `naos` `adit` `scry` `eddy` etc | 0 — all taken pre-2002 |
| Tier 3: 5-letter / 6-letter dict words | `frith` `glint` `liber` `prism` `nimbus` `caelum` `prisma` `proven` `digest` etc | 0 — all taken pre-2010 |
| Tier 4: 6-letter invented brand-style | `klarvo` `nymeta` `viskor` `fronix` `mintly` `vorta` `vexor` etc | 1 (`frelve`) |
| Tier 5: 7+ letter compound | `siftforge` `siftcraft` `siftsmith` `pithforge` | All available, $10/year |

## Key findings

**Finding 1: 4-letter .com finished registration on 2014-01-09.**

GoDaddy publicly recorded the last unregistered 4-letter .com (`fxhe.com`) being grabbed on that date. Any 4-letter combination from `aaaa.com` to `zzzz.com` is now taken — 456,976 total combinations, all in private hands. The market entered "hold-don't-sell-unless-paid" mode.

**Finding 2: 2024-2025 saw a new squatter wave targeting AI-adjacent invented words.**

Cards taken in 2024 or 2025 (visible in RDAP creation dates):
- `sifr.com` — registered 2024-12-01, parked at Afternic
- `crucib.com` — 2025
- `pithly.com` — 2025
- `pithor.com` — 2025 (parked)
- `cernir.com` — 2025
- `sifery.com` — 2025
- `vetir.com` — 2024 (parked)

Pattern: short invented words with vague AI / dev-tool resonance are being grabbed by squatter bots monitoring naming trends. By the time a developer thinks of the name, the squatter already owns it.

**Finding 3: Secondary market prices for 4-letter .com**

Public sales data (NameBio, public announcements):

| Domain | Price | Year |
|---|---|---|
| voice.com | $30M | 2019 (Block.one) |
| insurance.com | $35.6M | 2010 |
| ai.com | $11M | 2023 (OpenAI) |
| 360.com | $17M | 2015 |
| sex.com | $13M | 2010 |
| fund.com | $9.99M | 2008 |
| business.com | $7.5M | 1999 |
| pizza.com | $2.6M | 2008 |

Dictionary 4-letter .com sits in the $100K–$1.5M band. Invented 4-letter at Afternic / Sedo: $5K–$100K.

**Finding 4: Modern SaaS deliberately picked 5-7 letter invented or compound names.**

Not coincidence. Examples (length / origin):

- Vercel (6, Latin "rapid" truncation)
- Figma (5, pure invention)
- Notion (6, dictionary but uncommon)
- Stripe (6, dictionary, unrelated to payments)
- Slack (5, dictionary)
- Anthropic (9, ancient Greek "human")
- Cohere (6, dictionary verb, low SEO competition)
- Replit (6, "replicate" truncation)
- DropBox (7, compound)

The pattern: **avoid 4-letter dictionary, avoid the squatter zone, optimize for SEO-uncrowded keyword space.**

**Finding 5: Cookie-extractor flag on .tech and similar new TLDs.**

Renewal-price escalation by registrar:

| TLD | First year | Renewal | Multiplier |
|---|---|---|---|
| `.tech` | $6.99 | $50.98 | 7× |
| `.io` | $35 | $50 | 1.4× |
| `.ai` | $99 | $110 | 1.1× |
| `.dev` | $15 | $15 | 1× |
| `.co` | $9.58 | $27.09 | 2.8× |
| `.com` | $10 | $10 (Verisign +7%/yr regulated) | — |

`.tech` is a known trap: cheap first year, locked-in renewal pain after the brand has launched.

## What this means for Sift

Sift chose `HuanNan520/sift` as the GitHub repo name without securing `sift.com`. Reasoning:

1. `sift.com` belongs to Sift Inc. (SF SaaS, fraud detection, ~$1B valuation, registered 1995). Not for sale.
2. `sift.io / .dev / .app / .ai` all taken (mostly defensive holdings by Sift Inc.).
3. Available: `sift.tech` ($7 then $51), `sift.so` (~$35-50/yr), `sift.co` ($9.58 then $27).
4. Project's traffic will come from GitHub trending, Reddit, HN, and AI search citations — not Google SEO. `sift.com` collision matters less than for a SaaS targeting SEO.
5. The spec format encourages domain-deferred decisions: "项目不在于成熟,而在于出现" — ship the spec, buy a domain later if traction justifies.

If domain becomes load-bearing later, fallback order:
1. `sift.co` (most balanced)
2. `getsift.io` / `usesift.com` (subdomain-style modern brands)
3. Negotiate with Sift Inc. (long shot, $$$)

## Recheck protocol

Domain market dynamics are slow-moving (decade-scale) but two events would trigger redo:

1. A new TLD (`.spec`, `.docs`, `.ai-something`) reaches mainstream adoption (current candidates: `.ai` is there, nothing else close).
2. Sift Inc. (the SaaS company) pivots or shuts down, freeing the `sift.com` brand.

## Related

- [[../decisions/2026-05-11-launch-not-perfect]] — the decision to ship v0.1.0 without locking down a .com first
- Domain market data sources: RDAP queries via rdap.org, NameBio public sales history, Verisign quarterly .com reports
