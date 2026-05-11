# Quickstart

Get a Sift-compliant vault running in 10 minutes. Works with any Obsidian + Claude Code setup.

This is the "I read the README, what do I actually do now" page.

## Prerequisites

- An Obsidian vault (or any folder of markdown files you want to organize)
- Claude Code installed (`claude` CLI) — though the spec works with any AI agent
- 10 minutes

## Step 1: Create the four card folders

Inside your vault, add the four mandatory directories:

```bash
cd /path/to/your/vault
mkdir -p skills/{research,debug,scripts,decisions}
```

If your vault is fresh, you can use a different top-level layout. The point is that the four card types stay separated — not their exact path.

## Step 2: Copy the templates

Grab the template files from this repo into your vault's templates location:

```bash
# from the sift repo root
cp templates/*.template.md /path/to/your/vault/templates/
```

When you sink your first card, copy the relevant template, rename it to `YYYY-MM-DD-slug.md`, and fill it in.

## Step 3: Add `_CLAUDE.md` and `index.md` to the vault root

These two files tell future AI sessions what your vault is and how it's organized. Minimal versions:

```markdown
<!-- _CLAUDE.md -->
---
type: vault-manual
date: 2026-05-11
ai-first: true
audience: claude
---

## For future Claude

This vault follows the Sift spec (https://github.com/HuanNan520/sift).
Four card types in `skills/{research,debug,scripts,decisions}/`.
Frontmatter rules: see Sift SPEC.md §3.

Sink triggers:
- research: parallel-agent or multi-source investigation > 30 min
- debug: non-trivial problem fix > 5 min  
- scripts: reusable code > 10 lines
- decisions: trade-off you'd want the rationale for
```

```markdown
<!-- index.md -->
---
type: index
date: 2026-05-11
ai-first: true
---

## For future Claude

Catalog of cards. Read this first to know what exists without grepping everything.

### research/
(none yet)

### debug/
(none yet)

### scripts/
(none yet)

### decisions/
(none yet)
```

Update both files whenever you add a card.

## Step 4: Tell Claude Code about the vault

Add a section to your `~/CLAUDE.md` (the global one) so any new session knows the vault exists and how to use it:

```markdown
## My private SKILL library at ~/vault/

Before dispatching a research agent on a topic, first grep `~/vault/skills/research/`.
If a non-stale, non-triggered card exists, reuse the conclusion.
If a stale or triggered card exists, pass it to the new agent as baseline.

Sink a new card when one of these triggers fires:
- research: parallel-agent investigation > 30 min
- debug: > 5 min to solve a non-trivial bug
- scripts: > 10 lines, reusable
- decisions: trade-off with multiple viable options

Cards must follow https://github.com/HuanNan520/sift SPEC.md.
```

## Step 5: Sink your first card

Wait for the next time you (or Claude on your behalf) solves something that crosses a trigger. Then:

1. Copy the matching template (`templates/debug.template.md` etc.)
2. Rename: `vault/skills/debug/2026-05-11-thing-you-solved.md`
3. Fill in the frontmatter and section bodies
4. Update `vault/index.md` to add a one-line pointer to the new card

Done. The vault now has one card and one index entry. Repeat the next time a trigger fires.

## What changes after a few weeks

Concretely, what you'll notice:

- **Claude sessions start faster.** When you open a new conversation and ask about something you've worked on before, Claude greps `skills/` and pulls up the relevant card. No re-explanation.
- **Research becomes cumulative.** Investigations you ran weeks ago surface automatically when their topic comes up again. The `expires` + `recheck-trigger` discipline means stale findings get flagged for refresh instead of silently re-cited.
- **Debug knowledge compounds.** The same bug pattern (auth token expired, file watcher stops, dependency mismatch) shows up across projects. After two or three sinks, Claude recognizes the pattern early.
- **Decisions become legible.** Three months later, when you wonder "why did we pick X over Y", the answer is in `decisions/`, written by you when the context was fresh.

The change is gradual — not a dramatic flip from "Claude ignores my notes" to "Claude is my second brain". It's more like: each new conversation has 20-30% less re-explanation than the last.

## When NOT to use Sift

Skip the spec if:

- You're a heavy personal journaler. Sift is for engineering / research knowledge, not daily mood logs or stream-of-consciousness writing.
- Your vault is one person and stays that way forever. The discipline pays back over months — if you're going to abandon the vault in a week, the overhead isn't worth it.
- Your "knowledge" is mostly bookmarks. Sift wants synthesized cards with root causes and recheck triggers, not link dumps.
- You want a team wiki. Sift is single-user. Multi-user vaults are an open problem.

## Examples to copy from

Three real cards extracted from a vault running these principles in production (private details redacted):

- [examples/research-example.md](./examples/research-example.md)
- [examples/debug-example.md](./examples/debug-example.md)
- [examples/decision-example.md](./examples/decision-example.md)

And the Sift repo itself runs the spec on itself:

- [meta/research/](./meta/research/) — investigations the maintainer ran while building Sift
- [meta/decisions/](./meta/decisions/) — design choices made along the way
- [meta/debug/](./meta/debug/) — non-trivial problems solved during development

These are the same templates filled in, not separate documentation. Read them as worked examples of what Sift cards look like under real load.

## Getting help

- Open an issue at https://github.com/HuanNan520/sift/issues
- Read the full spec: [SPEC.md](./SPEC.md)
- Read the philosophy: [README.md](./README.md)
