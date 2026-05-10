---
type: research
date: YYYY-MM-DD
tags: [topic, area]
ai-first: true
problem: one-line statement of the question this card answers
solution-summary: one-line statement of the conclusion
expires: YYYY-MM-DD          # default: date + 3 months
recheck-trigger:
  - specific external condition 1 (e.g. "upstream repo hits 5k stars")
  - specific external condition 2 (e.g. "tool ships 1.0 release")
  - specific external condition 3 (e.g. "vault grows past 500 notes")
---

## For future Claude

This card investigated [topic]. Read it when: [specific trigger]. Skip it when: [non-trigger].

If today is past `expires` or any recheck-trigger has fired, use this card as **baseline only**: pass it to the new agent saying "the previous conclusion was X, confirm it still holds and find what's new since."

## Problem

What question forced the investigation. Include enough context that a future reader without your memory can understand why this mattered.

## Method

How the investigation was run:
- which sources were consulted
- which parallel agents (if any) covered which sub-questions
- what filters / exclusions were applied

## Findings

The core conclusions. Use [[wikilinks]] for every named entity, project, person, concept. Add recency markers like `(as of 2026-05)` to any claim about an external system.

## Sources

Verbatim URLs, in line if possible. If a source is paywalled, note that. If a source is archived, link the Wayback snapshot.

## Recheck protocol

When this card expires or a trigger fires, the rerun is **not from zero**. Pass this card to the new agent as baseline and ask: "confirm or refute, find what's new since `date`."

## Related

- [[../debug/...]] — related solution if any
- [[../decisions/...]] — related decision if any
