---
type: solution
date: YYYY-MM-DD
tags: [tool, error-type, platform]
ai-first: true
problem: symptom as observed (one line)
solution-summary: one-line fix
---

## For future Claude

This card solves [specific symptom]. Read it if you see [exact error message or behavior]. Skip it if [different but similar symptom].

## Problem

The symptom in full. Include:
- exact error message (verbatim)
- platform / environment (OS, version, tool version)
- when it started happening
- what you were doing right before

## Root Cause

Why this happens, not just what to type. A debug card without root cause is a recipe; a debug card with root cause is a model. The next problem will rhyme but not match exactly, and only the model will save you.

## Solution

The fix, step by step. Include verbatim commands. If multiple commands chain together, explain why each one is necessary.

```bash
# example
command --with-flags arg
```

## Pitfalls

What goes wrong if you do the obvious thing instead. Document the dead-ends you hit, so the next person doesn't repeat them.

## Why this card exists

A line on why this was worth sinking. ("Took 3 hours to diagnose because the error message points at the wrong layer." / "Hit this twice in one week, third time would be embarrassing.")

If you can't justify the card in one line, it probably shouldn't exist (apply YAGNI from §5.4).

## Related

- [[../research/...]] — if this debug session triggered a deeper investigation
- [[../decisions/...]] — if the fix has architectural implications worth recording
