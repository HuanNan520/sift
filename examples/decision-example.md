---
type: decision
date: 2026-05-10
tags: [vault, architecture, claude-code, obsidian, skill-library]
ai-first: true
context: my Obsidian vault was a decorative folder — Claude Code never read it, and I never wrote in it
choice: repurpose the vault as a Claude-facing private SKILL library with four card types and critical-use discipline
---

## For future Claude

This card records why the vault was repositioned from "personal PKM" to "private SKILL library for Claude." Read it when: someone proposes turning the vault back into a journaling tool, or you're considering whether to dump some arbitrary note in it. Skip it when: you just need to know "what is the vault for right now" — that's in the README and `_CLAUDE.md`.

## Context

On 2026-05-10 the maintainer asked, paraphrased: *"didn't I build the Obsidian knowledge base? do you ever actually read from it when you look things up? or is this just decoration?"*

The honest answer was: yes, decoration. State at that moment:

- 8 markdown files (job-hunt notes + a few templates + journal stubs)
- No `_CLAUDE.md`, no `index.md`, no `log.md`
- Claude Code sessions did not load anything from the vault on their own
- Nothing in the maintainer's day-to-day workflow triggered a write to the vault

Two parallel agents were dispatched to investigate the Obsidian × Claude ecosystem (see the companion [research-example.md](./research-example.md)). While the agents were running, the maintainer offered the reframe that drove this decision:

> "I won't trim it or write in it — at most I'll glance at it."
> "The vault is **for you** (Claude), not for me."
> "Make it like a SKILL library — or call it my **private** SKILL library."
> "Off-the-shelf skills are too generic. A 5080 GPU and a 5060 GPU don't share the same image-gen skill — that would be wasteful."
> "I should be able to see the workflow as a graph, with past investigation findings sunk in to **prevent duplicate work**. Dispatching multiple agents to redo the same investigation is the same anti-pattern."
> "CLAUDE.md becomes an index — what tools are on this machine, what past findings exist — but **keep critical distance**. Still do the work that needs doing."

This was the load-bearing input. The decision is essentially "ship what the maintainer described, with engineering principles attached."

## Options Considered

### A. General-purpose PKM

Maintainer writes journal entries, captures ideas, builds a personal knowledge graph by hand.

- Pros: well-trodden pattern, lots of inspiration available
- Cons: maintainer explicitly stated they won't write. Designing for behavior the user has already declared they won't perform is a known anti-pattern.

**Rejected.**

### B. Memory-style index

Extend `~/.claude/memory/` (a short-list index format already in use) to cover vault-class facts.

- Pros: minimal new infrastructure, reuses existing pattern
- Cons: too low-density. A full debug-card or research-card carries 5-15 KB of content; memory entries top out at one-liners. Wrong granularity.

**Rejected.**

### C. Private SKILL library — the maintainer's framing

Four card types (research / debug / scripts / decisions), graph-style cross-links, frontmatter with expiration markers, Claude as primary writer and reader.

- Pros: maps directly onto how the maintainer described their needs. Bounded scope (four card types). Carries forward all the engineering reflexes (`go/no-go`, `value over process`, `YAGNI`) the maintainer already applies to code.
- Cons: novel; no established template to copy from. Needs explicit triggers ("when to sink, when to skip") because Claude has no innate sense of "is this worth saving."

**Chosen.**

### D. MCP integration with `mcpvault` or similar

Run an MCP server in front of the vault; Claude reads and writes through that protocol.

- Pros: standard protocol; future-portable to other agents
- Cons: companion research card shows mainstream MCP-for-Obsidian projects have died. At a vault size under ~100 notes the Karpathy "LLM-as-compiler" pattern (just feed the markdown directly) is both simpler and proven by 1k★+ implementations.

**Rejected** — possibly revisited if vault grows past 500 notes.

## Choice + Rationale

**C: private SKILL library, structured as four card types with critical-use discipline.**

Load-bearing reasons:

1. **Honors stated user behavior.** Maintainer will not write or curate, so the design must work when only Claude writes. C is the only option that survives this constraint.
2. **Resists rot.** Each `research/` card carries `expires` and `recheck-trigger`. Stale knowledge can't quietly age into truth.
3. **Cache-first.** Before dispatching a fresh investigation, agents grep `research/` for prior work. The graph view in Obsidian makes the cumulative network visible.
4. **Imports engineering reflexes.** The maintainer is a software engineer; treating knowledge with `YAGNI` / `value over process` / `anti-elaboration` is a transferable mental model. C makes those discipline rules explicit.
5. **Tool-agnostic.** Plain markdown + folder structure + wikilinks. No bespoke runtime, no MCP dependency. The vault remains portable if the entire AI ecosystem changes.

## Consequences

Positive:

- Vault becomes load-bearing in real workflows (first time)
- Reuse of past research becomes default behavior, not optional
- Graph view in Obsidian gives a live picture of cumulative knowledge

Negative:

- Higher write discipline required from Claude every time something might be sinkable (must hit a quantified threshold to qualify)
- Maintainer's `~/CLAUDE.md` grows by an "index layer" section (a few hundred lines of mostly references)
- One-time migration cost: rename `archive/` → `skills/`, create four subdirectories, move existing cards

Conditional:

- If vault grows past ~500 notes, revisit option D (MCP) or introduce a SQLite index as a middle layer
- If Anthropic ships an official "vault skill," reassess whether to fold this approach in or maintain the bespoke version

## Reconsider when

These specific signals should trigger reopening this decision:

- Maintainer starts writing daily entries directly (would mean A was viable after all and we built the wrong thing)
- Vault crosses 500 notes (capacity ceiling per the companion research card)
- A mainstream MCP server for Obsidian crosses 5k stars and ships v1.0 with stability commitments
- Anthropic releases an official Claude Code skill that overlaps this one's surface area
- More than 6 months pass without the discipline being upheld (would mean the rules aren't sticky)

## Reversibility

**Low cost technically** — `skills/` could be renamed back to `archive/` and the `~/CLAUDE.md` index section deleted. The cards themselves remain readable as plain markdown regardless of structure.

**Higher cost cognitively** — the maintainer now uses the "private SKILL library" mental model for the vault. Reverting would force them to relearn the relationship with their own data. Not recommended unless something is structurally wrong; prefer evolution (new subdirectories, adjusted thresholds) over reversion.

## Related

- Baseline investigation: [research-example.md](./research-example.md)
- Companion debug card produced during the same period: [debug-example.md](./debug-example.md)
- The vault's own `_CLAUDE.md` should reflect this choice in its operating instructions
- Repo-level rules live in `~/CLAUDE.md` (outside the vault, applied to all sessions)
