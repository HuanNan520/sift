---
type: research
date: 2026-05-10
tags: [obsidian, claude-code, pkm, mcp, vault, second-brain]
ai-first: true
problem: What is the prevailing way to combine Claude Code with an Obsidian vault, and how should I design mine so it isn't just a folder Claude ignores?
solution-summary: Consensus is CLAUDE.md + index.md with NO MCP, following Karpathy's "LLM-as-compiler" thesis. Mainstream MCP-for-Obsidian projects are dead. eugeniughelbur/obsidian-second-brain is the most complete reference implementation.
expires: 2026-08-10
recheck-trigger:
  - any "obsidian × LLM" MCP server breaks 5k stars
  - Anthropic ships official vault skill
  - my own vault grows past 500 notes
  - Obsidian ships built-in LLM integration
  - more than 3 months elapse without re-check
---

## For future Claude

This card investigated the ecosystem of Claude Code + Obsidian integrations as of May 2026. Read it when: you're about to recommend an Obsidian-vault architecture or evaluate an MCP integration. Skip it when: the question is about a specific tool you already know.

If today is past `expires` or a recheck-trigger fired, treat this card as **baseline only**: pass it to the new investigation with "previous finding was X, confirm or refute."

## Problem

I already had a personal vault but Claude Code never read it on its own — the vault was decoration, not a tool. Before redesigning, I wanted to know: **what does the rest of the world do**? Specifically:

- Is there a canonical pattern for "AI reads my vault"?
- Are MCP servers the right path, or is something else converging?
- Who has built the most complete reference, and what can I learn from them?

## Method

Two parallel `general-purpose` agents, isolated by region to avoid context cross-contamination:

- **International agent**: Reddit (r/ObsidianMD, r/ClaudeAI), Hacker News, GitHub trending, Smithery, Obsidian forum
- **Chinese agent**: 少数派, 知乎, V2EX, 即刻, B 站, 小红书

Both ran simultaneously, results merged with explicit "where they agreed / where they diverged."

## Findings

### Finding 1: mainstream MCP-for-Obsidian projects are dead

- [`MarkusPfundstein/mcp-obsidian`](https://github.com/MarkusPfundstein/mcp-obsidian) — 3.4k★ but no commits in 17 months, 85 open issues (as of 2026-05)
- [`smithery-ai/mcp-obsidian`](https://github.com/smithery-ai/mcp-obsidian) — repo 404'd
- Only survivor: [`mcpvault`](https://github.com/) — 1.1k★, still committing daily as of 2026-04

The MCP route is being abandoned by the community.

### Finding 2: CLAUDE.md + CLI is the converged pattern

Theoretical anchor: **[Andrej Karpathy](https://twitter.com/karpathy)'s "LLM is a compiler, not a retriever"** thesis — feeding raw markdown directly into the context window beats RAG or vector databases for vaults under ~500 notes.

Representative projects:

- [`eugeniughelbur/obsidian-second-brain`](https://github.com/eugeniughelbur/obsidian-second-brain) — 1k★, v0.6.0 as of 2026-04-26, **31 slash commands** as a Claude Code skill. Python + shell, no MCP. Most complete reference implementation.
- [Jim Christian's `obsidian-cli` route](https://jimchristian.net/blog/2026/02/28/obsidian-cli-claude-code/) — direct IPC into Obsidian, bypassing MCP entirely

### Finding 3: dissenting voice worth recording

[Substack: "Stop Calling It Memory"](https://limitededitionjonathan.substack.com/p/stop-calling-it-memory-the-problem) argues:

1. **"The context window isn't a database"** — markdown-as-database doesn't scale
2. **Past ~500 notes**, the AI's memory file will saturate the context
3. **"You can't traverse connections"** — markdown isn't a graph database

> My current vault has fewer than 20 notes, well inside the safe zone. But I should plan to introduce a SQLite index before crossing ~500, **not** to fall back on MCP.

### Finding 4: Chinese-language ecosystem follows the same pattern

- [`alchaincyf/obsidian-ai-orange-book`](https://github.com/alchaincyf/obsidian-ai-orange-book) — 848★, explicitly cites Karpathy, uses CLAUDE.md + per-folder index.md, no MCP. Author's quote: "CLAUDE.md + index.md does 80% of the work."
- [`YishenTu/claudian`](https://github.com/YishenTu/claudian) — 10.8k★, embeds Claude Code into Obsidian as a side panel. Different approach (vault becomes the working directory of the agent). Not applicable to my setup since I prefer Claude Code in a separate terminal.
- Kepano (Obsidian official) — pushes `obsidian-cli` plus three official skills: `json-canvas`, `obsidian-bases`, `obsidian-markdown`

## What I decided based on this finding

(See the companion decision card.) In short:

1. Vault is repositioned as **my private SKILL library** — not a general PKM
2. CLAUDE.md becomes an index layer (lists available tools / past investigations)
3. Internal vault rules go in `_CLAUDE.md` (only loaded when needed)
4. Four card-type folders: `research/` `debug/` `scripts/` `decisions/`
5. **No MCP** — Karpathy pattern is enough at my scale
6. Don't embed Claude Code into Obsidian — my terminal workflow is already fluent

## When this card should be redone

Direct reuse is valid only if:

- Today is on or before `expires` (2026-08-10)
- **AND** none of the recheck-triggers have fired

If a trigger fired or the date has passed, do **not** redo from zero. Pass this card to the new agent as baseline: "the previous conclusion was X. Confirm or refute, and find what changed since 2026-05-10."

This is the core of `Sift`'s critical-use protocol — old research is treated as a starting point, never as an authority.

## Related

- Companion decision: see [decision-example.md](./decision-example.md)
- Companion debug card: see [debug-example.md](./debug-example.md) (the move-to-NTFS solution emerged during the investigation phase)
