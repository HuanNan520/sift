---
name: Feature request
about: Propose an addition or change to the spec
title: '[spec] '
labels: enhancement
assignees: ''
---

## What you're proposing

One-sentence summary. E.g.:

- "Add a fifth card type for `incidents/` (separate from `debug/`)"
- "Drop the mandatory `## For future Claude` preamble for cards under 200 words"
- "Allow `expires: never` for foundational decisions that don't have a renewal cycle"

## Sink trigger this enables

Sift's discipline is that adding spec surface area needs a justifying trigger. What real situation would benefit from this addition that the current four card types can't handle?

If you can give a concrete worked example (a card you'd write under the new rule), that's the strongest pitch.

## Engineering principles check

Sift applies four principles to itself: `go/no-go gating`, `anti-elaboration`, `value over process`, `YAGNI`. Answer these:

- **Is this the second occurrence?** (YAGNI: first occurrence is anecdotal, not a pattern)
- **Does it add lines or remove them?** (anti-elaboration prefers removal)
- **What value transfers to a future reader?** (value over process: not just "completeness")
- **What's the cost?** (go/no-go: spec readers spending time understanding new rules)

If three out of four point toward "no", the proposal is unlikely to land.

## What you've considered

- Are there existing card types or rules that cover this case partially?
- What's the workaround today, and why is it inadequate?
- Have you seen prior art (e.g. Karpathy's LLM wiki gist, or other AI-vault writeups) handle this differently?

## Additional context

Anything else.
