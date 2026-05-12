#!/usr/bin/env python3
"""Sift sink-watcher: polling-watch jsonl directory, when a *.jsonl file's
mtime stops changing for SETTLE_SECONDS dispatch it to sift-sink-agent
--worker for sink judgment.

Designed for sift-server deployment (fnos / future cloud VPS) under systemd.
Stays alive, serial-dispatches sinks (one LLM call at a time to avoid rate
limits), logs to $SIFT_LOG_DIR/sift-sink-watcher.log.

Uses pure-Python polling (no inotify-tools / no watchdog lib dep) — fits the
sift stdlib-only constraint. Poll interval = 2s · settle window matches the
realistic session close cadence (no need for sub-second latency).

Env:
  SIFT_JSONL_ROOT (default /vol1/1000/sift/jsonl)
  SIFT_LOG_DIR    (default /vol1/1000/sift/logs)
  SIFT_WATCH_SETTLE_SECONDS (default 10) — mtime must stay stable this long
  SIFT_WATCH_POLL_SECONDS   (default 2)  — directory rescan interval
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _envpath(name: str, default: Path) -> Path:
    v = os.environ.get(name, "")
    return Path(v) if v else default


JSONL_ROOT = _envpath("SIFT_JSONL_ROOT", Path("/vol1/1000/sift/jsonl"))
LOG_DIR = _envpath("SIFT_LOG_DIR", Path("/vol1/1000/sift/logs"))
LOG_PATH = LOG_DIR / "sift-sink-watcher.log"
SINK_AGENT = Path(__file__).parent / "sift-sink-agent.py"
SETTLE_SECONDS = int(os.environ.get("SIFT_WATCH_SETTLE_SECONDS", "10"))
POLL_SECONDS = int(os.environ.get("SIFT_WATCH_POLL_SECONDS", "2"))
SINK_TIMEOUT = int(os.environ.get("SIFT_SINK_TIMEOUT", "300"))  # 5 min per sink


def log(msg: str):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [sink-watcher] {msg}\n")
    except Exception:
        pass


def process_jsonl(p: Path):
    if not p.exists() or not p.is_file():
        log(f"skip: not a file {p}")
        return
    payload = json.dumps({
        "transcript_path": str(p),
        "session_id": p.stem,
    })
    try:
        result = subprocess.run(
            ["python3", str(SINK_AGENT), "--worker"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=SINK_TIMEOUT,
        )
        if result.returncode != 0:
            log(f"sink fail: {p.name} rc={result.returncode} err={result.stderr[:200]}")
        else:
            log(f"sink dispatched: {p.name}")
    except subprocess.TimeoutExpired:
        log(f"sink timeout: {p.name}")
    except Exception as e:
        log(f"sink exception: {p.name} {e}")


def watch_loop():
    """Poll JSONL_ROOT recursively for *.jsonl files. Track each file's mtime.
    When a file's mtime stops changing for SETTLE_SECONDS, dispatch it (once).
    Subsequent mtime changes re-arm the file for another dispatch.
    """
    JSONL_ROOT.mkdir(parents=True, exist_ok=True)
    seen: dict[str, tuple[float, float, float]] = {}  # path -> (mtime, first_seen_at, last_dispatched_mtime)

    # Init scan: mark every existing *.jsonl as "already dispatched at current
    # mtime". Restart safety — without this, every existing file would re-dispatch.
    # Only mtime changes after init will trigger dispatch.
    now0 = time.time()
    init_count = 0
    for p in JSONL_ROOT.rglob("*.jsonl"):
        try:
            st = p.stat()
            seen[str(p)] = (st.st_mtime, now0, st.st_mtime)
            init_count += 1
        except FileNotFoundError:
            continue
    log(f"start polling {JSONL_ROOT} (poll={POLL_SECONDS}s, settle={SETTLE_SECONDS}s, agent={SINK_AGENT}) · pre-seen {init_count} existing jsonl as dispatched")

    while True:
        now = time.time()
        try:
            for p in JSONL_ROOT.rglob("*.jsonl"):
                try:
                    st = p.stat()
                except FileNotFoundError:
                    continue
                key = str(p)
                cur_mtime = st.st_mtime
                prev = seen.get(key)
                if prev is None:
                    seen[key] = (cur_mtime, now, 0.0)
                    continue
                prev_mtime, first_seen_at, dispatched_mtime = prev
                if cur_mtime != prev_mtime:
                    # mtime changed → re-arm settle window
                    seen[key] = (cur_mtime, now, dispatched_mtime)
                    continue
                # mtime stable; check settle window and not already dispatched at this mtime
                if cur_mtime == dispatched_mtime:
                    continue
                if (now - first_seen_at) >= SETTLE_SECONDS:
                    log(f"stable mtime, dispatch: {key}")
                    process_jsonl(p)
                    seen[key] = (cur_mtime, first_seen_at, cur_mtime)
        except Exception as e:
            log(f"watch_loop error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        watch_loop()
    except KeyboardInterrupt:
        log("interrupted")
        sys.exit(0)
    except Exception as e:
        log(f"top-level: {e}")
        sys.exit(1)
