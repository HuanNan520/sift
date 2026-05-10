---
type: script
date: YYYY-MM-DD
tags: [language, domain]
ai-first: true
purpose: one-line statement of what the script does
---

## For future Claude

This script does [X]. Use it when [trigger]. Do not use it when [non-trigger]. Dependencies and platform assumptions below.

## Usage

```bash
# minimal invocation
./script.sh arg

# common variant
./script.sh --flag value
```

## Code

```bash
#!/usr/bin/env bash
set -euo pipefail
# ...full script here, verbatim
```

## Dependencies

- Tool A version X.Y or higher
- Tool B (specify install command if non-obvious)
- Platform: macOS / Linux / WSL2 — note any platform-specific behavior

## Why this card exists

One-line justification: when did you write this, why was it worth keeping, and how often do you expect to rerun it.

If the answer is "once a year, maybe never," apply YAGNI and don't sink.

## Pitfalls

- Anything that surprised you while writing it
- Anything that will surprise the next user
- Why you chose this approach over an obvious alternative

## Related

- [[../debug/...]] — if this script was born from a debug session
- [[../research/...]] — if a research card informed the design
