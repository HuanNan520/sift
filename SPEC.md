# Sift Spec

Version: 0.1.0 (draft)

This document is the canonical specification. README is the elevator pitch; SPEC is the contract.

---

## 1. Vault layout

A Sift-compliant vault has, at minimum, these four folders at its root:

```
vault/
├── research/      # investigations, with expiration
├── debug/         # solutions to non-trivial problems
├── scripts/       # reusable code snippets
└── decisions/     # project-level commitments
```

Optional sibling folders (out of scope for this spec):

```
vault/
├── _CLAUDE.md     # vault operating manual for the AI
├── index.md       # catalog of all cards
├── log.md         # chronological log of structural changes
└── templates/     # blank card scaffolds
```

---

## 2. Sink triggers

A piece of knowledge **only earns a card if it crosses one of these thresholds**:

| Card type | Trigger |
|---|---|
| `research/` | An investigation that required parallel agents, multiple sources, or more than 30 minutes |
| `debug/` | A non-trivial problem that took more than 5 minutes to diagnose and fix |
| `scripts/` | Code longer than 10 lines you'll plausibly run again, with non-obvious flags or setup |
| `decisions/` | A trade-off between two or more architectural / process options, where future-you would want the rationale |

**If a piece of knowledge does not cross its threshold, it does not get sunk.** It is allowed to be forgotten.

This is the heart of the spec. Most vault tools optimize for capture; Sift optimizes for *not* capturing.

---

## 3. Frontmatter schema

Every card MUST have YAML frontmatter at the top.

### 3.1 Required fields (all card types)

```yaml
---
type: research | debug | scripts | decisions
date: YYYY-MM-DD
tags: [lowercase, array, hyphenated]
ai-first: true
---
```

### 3.2 Type-specific fields

#### `research/` (mandatory)

```yaml
---
type: research
date: YYYY-MM-DD
tags: [...]
ai-first: true
problem: one-line statement of the question
solution-summary: one-line statement of the conclusion
expires: YYYY-MM-DD          # default: date + 3 months
recheck-trigger:
  - specific condition 1
  - specific condition 2
---
```

The `expires` and `recheck-trigger` fields are non-negotiable for research cards. The whole point of the spec is that **research conclusions decay** and the vault should know when its own knowledge is stale.

#### `debug/`

```yaml
---
type: solution
date: YYYY-MM-DD
tags: [...]
ai-first: true
problem: symptom as observed
solution-summary: one-line fix
---
```

Card body must include sections: `## Problem`, `## Root Cause`, `## Solution`, `## Pitfalls`. See [templates/debug.template.md](./templates/debug.template.md).

#### `scripts/`

```yaml
---
type: script
date: YYYY-MM-DD
tags: [...]
ai-first: true
purpose: one-line statement of what the script does
---
```

Card body includes the code, dependencies, and at least one usage example.

#### `decisions/`

```yaml
---
type: decision
date: YYYY-MM-DD
tags: [...]
ai-first: true
context: what situation forced the decision
choice: the option that was picked
---
```

Card body must include `## Options Considered`, `## Choice + Rationale`, `## Consequences`.

---

## 4. Mandatory writing rules

### 4.1 The `## For future Claude` preamble

Every card starts with a 2-3 sentence preamble addressed to the AI that will read it later:

```markdown
## For future Claude

This card is about X. Read it when: [trigger conditions]. Skip it when: [non-triggers].
```

This preamble exists because the vault is designed for **AI retrieval, not human reading**. When a future agent loads the vault, it scans preambles to decide what to read in full.

### 4.2 Wikilinks for every entity

Every person, project, concept, or named decision referenced in the body must be wrapped in `[[wikilinks]]`:

> "We chose [[postgres]] over [[mongodb]] because [[ali]] argued for SQL composability." 

This is for two reasons:
- Graph view (in Obsidian and similar tools) reveals relationships
- Future agents can grep `[[postgres]]` across the vault to find all related cards

### 4.3 Recency markers on external claims

Any claim about an external system (a library version, a tool's behavior, a market state) must carry a recency marker:

> "mcp-obsidian has 3.4k stars but has been untouched for 17 months (as of 2026-05)"

Without this, the claim ages silently.

### 4.4 Source URLs inline, verbatim

Cite sources at the point of claim, not at the bottom:

> "The benchmark in [Karpathy's gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) shows that LLMs reading raw markdown outperform RAG retrieval for vaults under 500 notes."

URLs preserved verbatim so they survive being copied out of the vault.

---

## 5. Engineering principles

These four principles, copied from software engineering, govern what does *not* get written:

### 5.1 Go/no-go gating

Before sinking, ask: "Is the future read-cost lower than the value I'm preserving?" If unclear, skip. A vault with 100 cards you read again is more valuable than 1000 cards you skim past.

### 5.2 Anti-elaboration

Short cards beat long ones. A sink is a value transfer, not a writing exercise. If you find yourself adding sections because they feel like they should exist, stop.

### 5.3 Value over process

Do not sink a debug card just because you solved a problem. Sink it because the *next* person who hits this problem (or the next instance of you) will save more than the read cost. The test is: would you want a stranger to find this card and benefit?

### 5.4 YAGNI

Speculative knowledge ("this might be useful someday") does not get a card. Wait for the second occurrence. The first time something happens, it's an event. The second time, it's a pattern. Only patterns deserve cards.

---

## 6. Critical-use protocol

When an AI agent reads the vault to answer a question, it MUST apply this protocol to every research card it cites:

1. Check `expires`. If today is past `expires`, the card is *stale* — do not cite it directly.
2. Check `recheck-trigger`. If any condition has fired, the card is *triggered* — do not cite it directly.
3. If stale or triggered, the card may still be used as **baseline** — but the agent must:
   - Acknowledge in its response that the source has aged
   - Either redo the relevant investigation, or flag explicitly that the answer is provisional

This protocol is what prevents the most common AI-vault failure mode: **rehearsing stale knowledge with the confidence of fresh research**.

---

## 7. Cache-first agent behavior

Before dispatching a new investigation (parallel agents, web search, deep research), agents MUST:

1. Grep the `research/` folder for relevant keywords
2. Read any non-stale, non-triggered card that matches
3. Reuse the conclusion if applicable

If a stale or triggered card matches, the agent may dispatch a new investigation **but must pass the old card as baseline context** to the new agent. This prevents redoing identical work from scratch.

---

## 8. What this spec deliberately omits

- **Tooling**. There is no installer, no daemon, no plugin. The spec is a contract, not a runtime.
- **Personal journaling**. Daily notes, mood logs, idea capture — out of scope. Use any tool you like.
- **Multi-user / team vaults**. v2 problem.
- **Specific AI agents**. Spec is agent-agnostic. Examples in this repo show Claude Code, but Cursor / Cline / Codex / your own agents work the same way.
- **Search infrastructure**. Plain grep over a folder of markdown files is the assumed baseline. If your vault outgrows that, you outgrow this spec.

---

## 9. Versioning

This spec follows [Semantic Versioning](https://semver.org). The version is in the file header.

- MAJOR: breaking change to the frontmatter schema or sink triggers
- MINOR: new optional field or new card type
- PATCH: clarification, examples, typos

v0.x means the spec is unstable and may change before v1.0.

---

## 10. Acknowledgements

The spec is built on top of:

- **Andrej Karpathy's "LLM as compiler" thesis** ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)) — markdown text directly into an LLM context beats RAG / vector retrieval for vaults under ~500 notes
- **Eugeniu Ghelbur's [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain)** — the AI-first frontmatter and `## For future Claude` preamble pattern. Sift extends his approach with the critical-use protocol and engineering principles
- Software engineering's accumulated wisdom on `YAGNI`, `go/no-go gating`, `value over process`, and `anti-elaboration`

If you're new to the AI-vault space, read Karpathy's gist first. If you want a vault-first reference tool, look at obsidian-second-brain. Sift is the spec these tools could implement.
