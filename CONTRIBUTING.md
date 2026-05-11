# Contributing to Sift

Thanks for considering a contribution. Sift is a draft spec at v0.x — breaking changes are on the table, so contributions of any size are welcome.

## What kind of contributions help most

In rough priority order:

1. **Real-world example cards.** The spec is more convincing with worked examples from different domains. If you've run Sift discipline in your own vault, opening a PR with a redacted card under `examples/` is high-value. Engineering, research, ops, design — anything.

2. **Spec clarifications.** If a section of `SPEC.md` left you guessing, that's a doc bug. Open an issue describing what you couldn't infer, or a PR that fixes the ambiguity.

3. **Tooling for the spec.** The `spec/sift.schema.yaml` is the start; linters, vault validators, "convert markdown folder to Sift layout" migration tools all extend the spec's reach. These can live in this repo or in adjacent ones.

4. **Translations.** The spec is currently English-only. Chinese, Japanese, Spanish, German contributions help reach non-English vault users.

5. **Critique.** Issues that argue against decisions made in the spec are welcome. Sift v0.x means design is open for revision. A PR or issue titled "the four-card carve doesn't survive [case]" is more useful than silent disagreement.

## What we apply Sift's own discipline to

The spec defines four engineering principles (`go/no-go gating`, `anti-elaboration`, `value over process`, `YAGNI`). We try to apply them to this repo too:

- **Go/no-go gating**: PRs that bloat the spec without obvious value get pushback. Specifically, scope creep into "Sift should also handle X" without a clear sink-trigger case for X.
- **Anti-elaboration**: short, focused PRs over sprawling rewrites. A PR with one clear goal is easier to review than ten loosely related changes.
- **Value over process**: a documentation PR that fixes a typo and adds zero readers can be merged. A documentation PR that rewrites a section because the writer prefers a different style needs to argue the reader value.
- **YAGNI**: "spec should support X someday" is not a reason to land X now. Wait for the second person who needs X, then revisit.

## How to open a PR

1. Fork the repo
2. Branch from `main`
3. Make the change
4. If the change touches the spec's behavior (sink triggers, frontmatter schema, writing rules), add a `meta/decisions/` card explaining the rationale
5. Open the PR with a clear description of the change and the user it serves
6. Tag with `type: docs` / `type: spec` / `type: tooling` / `type: example` to help triage

## What we won't merge

- Changes that make the spec longer without making it clearer
- Tooling that locks Sift to a specific vault tool (Obsidian, Logseq, etc.) when the spec is intentionally tool-agnostic
- Marketing additions (badges, social embeds, hype language in README)
- Sponsorship integrations until the project has a maintainer team to handle them

## Code of conduct

This project follows the [Contributor Covenant v2.1](./CODE_OF_CONDUCT.md). Be civil. Disagreement is welcome; ad hominem is not.

## License

Contributions are licensed under MIT (same as the rest of the repo).

## Recognition

Contributors are listed in `meta/decisions/` cards where their input shaped a decision, and in CHANGELOG entries where their PR landed. Sift doesn't currently maintain a separate AUTHORS file — the git history serves that purpose.

## Questions

Open an issue with the `question` label. For sensitive matters (security, code-of-conduct violations), see the contact in [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
