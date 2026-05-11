---
type: solution
date: 2026-05-10
tags: [obsidian, wsl, vault, file-watcher, ntfs, symlink, 9p]
ai-first: true
problem: Obsidian desktop crashes with EISDIR when opening a vault on \\wsl.localhost\ paths
solution-summary: Move the vault to Windows NTFS, expose it back into WSL via a symlink. All Linux-side tooling keeps working, Obsidian sees a native local path.
---

## For future Claude

This card solves the specific case where Obsidian's desktop app refuses to open a vault that lives inside a WSL2 home directory. Read it if you see `Error: EISDIR: illegal operation on a directory, watch` against a `\\wsl.localhost\` path. Skip it if the EISDIR is on a regular Windows path — that's a different problem.

## Problem

Setup:

- WSL2 Ubuntu-24.04 on Windows 11
- Obsidian desktop app freshly installed
- Vault lives at `~/vault/` (i.e. inside the Linux filesystem)

Action: open Obsidian → "Open folder as vault" → paste `\\wsl.localhost\Ubuntu-24.04\home\<user>\vault\`.

Obsidian shows a red error overlay on startup:

```
Failed to load Obsidian.
Error: EISDIR: illegal operation on a directory, watch '\\wsl.localhost\Ubuntu-24.04\home\<user>\vault\'
```

Clicking "Reload" loops the same error indefinitely.

## Root Cause

Obsidian uses Node.js `fs.watch` (under the hood: `chokidar`) to monitor vault changes. That maps onto OS-native filesystem notification APIs:

| Filesystem | Notification API | Works? |
|---|---|---|
| Windows local NTFS | `ReadDirectoryChangesW` | ✓ |
| Linux native ext4 | `inotify` | ✓ |
| **WSL `\\wsl.localhost\` (9P protocol)** | — | **✗** |

Microsoft exposes WSL2's Linux filesystem to Windows via a 9P file server. **The 9P protocol does not support change notifications**, so neither `ReadDirectoryChangesW` nor `inotify` works across that bridge. Obsidian registers a watcher on the vault root as one of the first startup steps; the failed call propagates and crashes the app.

References:

- [Obsidian forum: WSL can't open vault](https://forum.obsidian.md/t/wsl-cant-open-vault/56378)
- [microsoft/WSL #9412 — 9P does not support inotify](https://github.com/microsoft/WSL/issues/9412) — Microsoft's official guidance is "put the vault on a Windows filesystem"

## Solution

Physically move the vault to Windows NTFS. From inside WSL, replace the original path with a symbolic link pointing to the new location.

### Why this works

- Obsidian opens `E:\vault\` — a native NTFS path. `ReadDirectoryChangesW` works.
- WSL processes (Claude Code agents, hooks, scripts) read/write `~/vault/` — the symlink resolves to `/mnt/e/vault/`, which is `DrvFs` mounted ext-style. `inotify` works because the kernel still tracks Linux-side accesses.
- The 9P bridge is never used.

### Migration commands

```bash
set -e

# 1. cp the entire vault to NTFS (cross-filesystem so mv won't work)
cp -aR ~/vault /mnt/e/vault

# 2. verify size matches
echo "source: $(du -sh ~/vault/ | cut -f1)"
echo "destination: $(du -sh /mnt/e/vault/ | cut -f1)"

# 3. verify key files made it
for f in _CLAUDE.md index.md log.md; do
  [ -f "/mnt/e/vault/$f" ] && echo "OK $f" || { echo "MISSING $f"; exit 1; }
done

# 4. rename the original to a dated backup (don't delete until Obsidian confirms)
mv ~/vault ~/vault.bak.$(date +%Y%m%d)

# 5. create the symlink
ln -s /mnt/e/vault ~/vault

# 6. sanity check
head -1 ~/vault/_CLAUDE.md
```

### Opening Obsidian against the new path

1. Close the crashed Obsidian window
2. Obsidian → bottom-left Vault Manager → "Open folder as vault"
3. Paste the **NTFS path**, not the `\\wsl.localhost\` one:
   ```
   E:\vault
   ```
4. Trust author and enable plugins → done

## Pitfalls

**Things I tried that did not work**:

- "Open folder as vault" pointed straight at `\\wsl.localhost\...` — the original crash
- Disabling "File watcher" in Obsidian settings — there is no such toggle
- Editing Obsidian's vault config to refer to the 9P path — same crash

**Alternatives I considered but rejected**:

- **Vault stays in `/home`, Windows accesses via `\\wsl.localhost\`** — this is exactly the broken state
- **Vault in WSL, install Linux Obsidian inside WSL via WSLg** — input-method headaches for CJK languages, GUI performance noticeable
- **rsync mirror between two copies** — two-way sync conflict hell, no thanks

**The only stable solution** is vault-on-NTFS plus WSL symlink, which is what this card documents.

## Performance note

DrvFs reads/writes (WSL ↔ NTFS) are 30-50% slower than native ext4, with random IO more affected than sequential. For a vault under ~100 notes (a few MB), the difference is imperceptible.

If the vault grows past ~1000 notes with frequent full-text search, consider inverting: keep the vault on ext4 and run Obsidian inside WSL via WSLg. Until then, NTFS + symlink wins.

## Why this card exists

I lost two hours diagnosing this on first install. The error message points at a directory I/O issue, but the actual cause is a network protocol limitation three layers down. The next person who hits this should not have to repeat the trace.

## Related

- [research-example.md](./research-example.md) — the ecosystem investigation that informed how the vault was redesigned during this migration
- [decision-example.md](./decision-example.md) — the architectural decision about what the vault is *for*
