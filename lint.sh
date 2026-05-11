#!/usr/bin/env bash
# Sift vault linter — checks frontmatter compliance across a vault.
#
# Usage:
#   ./lint.sh [vault-path]              # defaults to current directory
#   ./lint.sh ~/my-vault
#
# Exits non-zero if any card fails validation. Useful in CI / pre-commit hooks.
#
# Requires: python3, pyyaml, jsonschema
#   pip install pyyaml jsonschema       # or use a venv
#
# The schema lives at spec/sift.schema.yaml relative to this script.

set -euo pipefail

VAULT="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA="$SCRIPT_DIR/spec/sift.schema.yaml"

if [[ ! -f "$SCHEMA" ]]; then
  echo "ERROR: schema not found at $SCHEMA" >&2
  exit 2
fi

python3 - "$VAULT" "$SCHEMA" <<'PY'
import sys, os, re, glob
try:
    import yaml
    from jsonschema import validate, ValidationError
except ImportError as e:
    print(f"ERROR: missing dependency ({e.name}). Install: pip install pyyaml jsonschema", file=sys.stderr)
    sys.exit(2)

# YAML 1.1 parses `2026-05-11` to datetime.date; we want strings so the schema's
# regex pattern can validate them. Override the timestamp constructor.
class StringDateLoader(yaml.SafeLoader):
    pass
StringDateLoader.add_constructor(
    'tag:yaml.org,2002:timestamp',
    lambda loader, node: loader.construct_scalar(node)
)

vault_path, schema_path = sys.argv[1], sys.argv[2]
schema = yaml.safe_load(open(schema_path))

# Find all card files under skills/{research,debug,scripts,decisions}/
# and meta/{research,debug,scripts,decisions}/ if present
card_dirs = []
for top in ("skills", "meta"):
    for sub in ("research", "debug", "scripts", "decisions"):
        d = os.path.join(vault_path, top, sub)
        if os.path.isdir(d):
            card_dirs.append(d)

if not card_dirs:
    print(f"no card directories found under {vault_path}/skills/* or {vault_path}/meta/*")
    sys.exit(0)

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

total = 0
passed = 0
failures = []

for d in card_dirs:
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        # skip templates
        if path.endswith(".template.md"): continue
        total += 1
        with open(path) as f:
            content = f.read()
        m = frontmatter_re.match(content)
        if not m:
            failures.append((path, "no YAML frontmatter found"))
            continue
        try:
            fm = yaml.load(m.group(1), Loader=StringDateLoader)
        except yaml.YAMLError as e:
            failures.append((path, f"YAML parse error: {e}"))
            continue
        try:
            validate(instance=fm, schema=schema)
            passed += 1
        except ValidationError as e:
            failures.append((path, f"{e.message} (at {'/'.join(str(p) for p in e.absolute_path) or 'root'})"))

print(f"\n  Sift lint: {passed}/{total} cards passed")
if failures:
    print(f"\n  {len(failures)} failures:")
    for path, msg in failures:
        rel = os.path.relpath(path, vault_path)
        print(f"    {rel}")
        print(f"      {msg}")
    sys.exit(1)
else:
    print(f"  all cards comply with sift.schema.yaml ✓")
PY
