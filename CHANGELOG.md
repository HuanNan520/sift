# Changelog

All notable changes to Sift are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Sift uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html); v0.x means the spec is unstable and breaking changes may land between minor versions.

## [Unreleased]

### Added

- `tools/recheck-agent.py` — LLM-driven complement to `recheck.sh`. Batch-scans vault cards, asks an LLM to verdict each as `keep` / `kill` / `merge` / `rewrite`, soft-deletes kills to `_trash/YYYY-WW/`, writes a markdown week report to `<vault>/sift/_reports/`. Defaults to `--dry-run`; `--execute` required to actually move files.
- `tools/recheck-agent.sh` — bash wrapper matching `lint.sh` / `recheck.sh` style.
- `QUICKSTART.md` — 10-minute setup guide for fresh Obsidian vaults
- `llms.txt` at repo root for AI crawlers (ChatGPT, Claude, Perplexity, AI Overviews)
- `CHANGELOG.md` (this file)
- `CONTRIBUTING.md` — contributor guide with sink-trigger discipline applied to PR scope
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- `.github/ISSUE_TEMPLATE/` — bug report and feature request templates
- `meta/research/2026-05-11-naming-com-exhausted.md` — the naming investigation that ran in parallel with v0.1.0 launch; documents why 4-letter .com is impossible to buy in 2026, why 2025 squatters target AI-adjacent invented words, and why Sift accepts not owning sift.com
- `meta/decisions/2026-05-11-launch-not-perfect.md` — the launch decision that produced v0.1.0 the same night the idea formed; records the option set, the rationale for shipping draft, the consequences, and the reconsider-when triggers
- `meta/debug/2026-05-11-cdp-social-preview-upload.md` — the CDP automation that uploaded the social preview banner (GitHub has no public API for this); documents five pitfalls including the `--remote-allow-origins` flag, the silent `DOM.setFileInputFiles` race condition, and the wrong-form-submission trap
- `spec/sift.schema.yaml` — machine-readable frontmatter schema for tooling; any Sift card can be validated with `yamllint --config spec/sift.schema.yaml`
- `lint.sh` — minimal lint runner that validates frontmatter compliance across a vault

### Changed

- README adds a `Quickstart` link near the top so first-time readers see the action path immediately
- README adds GitHub badges (license, stars placeholder, draft status)

## [0.1.0] — 2026-05-11

Initial public release.

### Added

- `README.md` — elevator pitch, the four card types, the four engineering principles, the critical-use protocol that distinguishes Sift from other AI-vault tools
- `SPEC.md` — full contract (vault layout, sink triggers, frontmatter schema per card type, mandatory writing rules, critical-use protocol, cache-first agent behavior, omitted scope)
- `LICENSE` — MIT
- `.gitignore` — standard exclusions
- `templates/research.template.md` — blank research card scaffold with mandatory frontmatter
- `templates/debug.template.md` — blank debug card scaffold
- `templates/scripts.template.md` — blank scripts card scaffold
- `templates/decisions.template.md` — blank decision card scaffold
- `.github/social-preview.png` — 1280×640 dark-mode banner (uploaded as the repo's GitHub social preview)
- `examples/research-example.md` — investigation into the Obsidian + Claude Code ecosystem, with `expires` and `recheck-trigger` in real use
- `examples/debug-example.md` — Obsidian EISDIR crash on WSL paths, root-caused to 9P protocol lacking inotify support
- `examples/decision-example.md` — repositioning a personal vault as a Claude-facing private SKILL library, with steelmanned rejected options and explicit reconsider-when triggers

### Notes

Initial release shipped from idea to public repo in 2.5 hours. v0.1.0 is explicitly draft — breaking changes may land in v0.2+ as feedback shapes the spec. See `meta/decisions/2026-05-11-launch-not-perfect.md` for the launch reasoning.
