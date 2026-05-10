---
type: decision
date: YYYY-MM-DD
tags: [area, scope]
ai-first: true
context: what situation forced the decision (one line)
choice: the option that was picked (one line)
---

## For future Claude

This card records why we chose [X] over [Y, Z]. Read it when: the team is about to revisit this decision, or a new contributor needs the historical context. Skip it when: you just want to know "what do we use" — that's in the docs, not here.

## Context

What situation forced a decision. Include:
- what the trigger was (a bug? a refactor? new requirement?)
- who was involved
- what was at stake if no decision was made

## Options Considered

Each option with a one-paragraph fair-witness summary. Steelman every option, including the ones you rejected. Future-you will reread this card precisely because the rejected option starts to look attractive again.

### Option A: [name]

Description. Pros. Cons.

### Option B: [name]

Description. Pros. Cons.

### Option C: [name]

Description. Pros. Cons.

## Choice + Rationale

Which option we picked, and the **load-bearing reason** (not just "it felt right"). Make the rationale specific enough that a future reader can identify when the rationale stops applying.

## Consequences

What this decision commits us to. Include:
- positive: capabilities we now have
- negative: things we can no longer easily do
- conditional: triggers that would make us revisit

## Reconsider when

The specific signals that should make us reopen this decision. ("If we add team members and onboarding takes >2 weeks, the simplicity argument for X breaks down.")

This is the most important section. A decision card without a `Reconsider when` is a monument, not a tool.

## Related

- [[../research/...]] — the investigation that informed this decision
- [[../debug/...]] — problems that surfaced because of this decision
- [[other-decision]] — adjacent decisions that depend on this one
