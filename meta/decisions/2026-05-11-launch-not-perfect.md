---
type: decision
date: 2026-05-11
tags: [launch, release-philosophy, mvp, perfect-is-enemy-of-good]
ai-first: true
context: facing the choice between polishing Sift into a complete v1.0 over weeks vs shipping a draft v0.1.0 the same night the idea emerged
choice: ship v0.1.0 the same night, public on GitHub, MIT licensed, README + SPEC + 4 templates + 3 examples + social preview. Let feedback shape v0.2+.
---

## For future Claude

This card records why Sift went public on day zero rather than after weeks of polish. Read it when: a similar project tempts a long pre-launch polish phase, or when "is this ready?" anxiety surfaces. Skip it when: the project at hand is a one-shot internal tool, not something seeking outside readers.

## Context

The spec's content came together inside a single 2.5-hour Claude Code session. Starting state at 05:30 local time:

- A broken symlink (`obsidian-second-brain` skill pointing at a wiped `/tmp` directory)
- No formal spec document anywhere — just a personal vault running discipline that I'd talked Claude into following
- No project name
- No domain
- No README
- No GitHub repo

Ending state at 08:08 local time:

- `HuanNan520/sift` public on GitHub, 3 commits, MIT licensed
- README + SPEC + LICENSE + 4 templates + 3 examples (real cards extracted from production vault, redacted)
- Social preview banner (1280×640, dark palette) generated and uploaded via CDP automation
- 10 GitHub topics for discovery

A reasonable engineering instinct says: "stop, polish, draft a v1.0 over the next two weeks, get feedback from 2-3 trusted readers, then publish." I rejected that instinct.

## Options considered

### A. Polish phase before public launch (the conservative path)

Spend 2-4 weeks privately iterating: send the draft to 3-5 friends in the AI/dev-tools space, refine based on their feedback, write a launch blog post, build a small website with examples, lock down a domain, write tooling that lints the spec.

Pros:
- v1.0 ships looking finished, not draft
- Initial feedback shapes the design before public commits
- No risk of being seen as "half-done" by first wave of readers

Cons:
- 2-4 weeks of unpaid solo polish on speculation
- Friends giving private feedback is a narrow channel; public traffic surfaces issues that polite friends don't
- High risk of the project never shipping at all — the "polish phase" can extend indefinitely
- The competitive window matters: the AI-vault space is moving fast; Karpathy's pattern is being adopted by multiple projects in parallel; getting the spec out **first** matters more than getting it out **perfect**

### B. Ship the same night, accept v0.x status (chosen)

Push README + SPEC + templates + examples + social preview to a public repo within hours of the idea forming. Mark it as draft (v0.1.0 with explicit "breaking changes possible before v1.0" notice). Let real-world feedback — issues, PRs, public discussion — drive v0.2 and beyond.

Pros:
- The project actually exists, publicly, with a URL someone can link to
- Feedback channel is broad: anyone reading can open an issue
- Establishes the spec's name and vocabulary in the ecosystem early
- Forces honesty: the README has to be readable as-is, not "after we polish it"

Cons:
- Public draft can attract criticism for things that would have been fixed in private polish
- Risk of looking unfinished to certain audiences (potential employers, academic readers)
- Breaking changes between v0.x versions are visible

### C. Private GitHub repo, share by URL with selected readers

Middle path: public-ish, but only invited readers, with intent to make fully public later.

Pros:
- Some external feedback without full exposure

Cons:
- Adds friction (invitation management)
- Loses the "publicly discoverable" benefit of B without much risk reduction over A

## Choice + Rationale

**B: ship the same night.**

Load-bearing reasons:

1. **The user (the project maintainer) explicitly framed it as "项目不在于成熟,而在于出现"** — the value of existing publicly outweighs the value of being polished. This is a deliberate philosophy, not a shortcut. The spec itself encodes engineering discipline ("anti-elaboration", "value over process"); applying that same discipline to the launch decision means picking B.

2. **The "polish phase" failure mode is documented**: projects that go into private polish often never ship. The longer the polish, the higher the stakes, the more excuses to delay. Public shipping resets that gravity.

3. **The competitive window is months, not years**. AI-vault tooling is moving fast. Eugeniu Ghelbur's `obsidian-second-brain` shipped its v0.6.0 publicly in April 2026 and accumulated 1k stars + 1374 clones within weeks. Multiple Chinese-language equivalents shipped in parallel. The longer Sift waits, the more its differentiated angle (critical-use protocol + engineering discipline + four card types) gets independently invented by others.

4. **v0.x is a license to be wrong**. Semantic versioning explicitly accommodates breaking changes in 0.x. Readers who understand versioning know that. The audience for a spec like this — developers, AI tooling builders — does understand it.

5. **The work was already substantive**: not "ship a stub README and figure it out later" but "ship a 5k-word README + 8k-word SPEC + 4 templates + 3 redacted real examples + visual banner". The v0.1.0 published was not a draft of the idea — it was a working contract.

## Consequences

Positive:

- Repo exists, has a URL, has a star count starting at 0, has a discoverable namespace
- Anyone reading this card a year from now can see the actual evolution from v0.1.0 → wherever it lands, with `meta/` recording the reasoning at each step
- The launch decision sets a precedent: future versions don't need to wait for polish either; ship often, iterate openly

Negative:

- v0.1.0 may have inconsistencies, gaps, awkward phrasing — those are visible in `git log` forever
- Early readers may form opinions based on the rough version and not return for v0.2
- The repo lacks operational scaffolding on launch (no CONTRIBUTING.md, no issue templates, no CHANGELOG, no lint tooling) — these get added in v0.2 but the v0.1 commit is permanent in history

Conditional:

- If public traffic surfaces a structural flaw in the spec (e.g., the four card types don't carve at the joints), a v0.2 redesign with breaking changes is acceptable — that's what v0.x means
- If feedback is largely silent (no issues, no engagement), the launch achieved discoverability anchor but not adoption; that's still better than not having launched

## Reconsider when

These specific signals should make us re-examine the "ship draft" strategy:

- A future iteration of Sift requires extensive coordination with other tools / specs and pre-launch alignment becomes load-bearing (e.g., a v2.0 designed jointly with another spec author)
- The repo accumulates 100+ stars but 0 issues / PRs — suggests the spec is read but not engaged with, meaning the early launch didn't unlock the feedback channel it was supposed to
- Sift is forked and the fork ships polished v1.0 first — would suggest the polish-first strategy was right after all

## Reversibility

**Not reversible.** Public commit history cannot be erased. But the alternative was a private repo never made public, which is also "not reversible" in the sense that the project simply doesn't exist for outside readers. The point is: B and A are both committing-to-something decisions, just in opposite directions. B commits to existing publicly; A commits to existing privately. B was the chosen commitment.

## Related

- [[../research/2026-05-11-naming-com-exhausted]] — the naming search that ran in parallel with this decision; the domain question was deferred because no perfect .com was available, which reinforced the "ship now, polish later" logic
- [[../debug/2026-05-11-cdp-social-preview-upload]] — one of the technical pieces that got built same-night to support the launch
- The project itself: [README.md](../../README.md) / [SPEC.md](../../SPEC.md)
