#!/usr/bin/env python3
"""Sift sink-watcher: inotify-watch jsonl directory, on close_write of *.jsonl
dispatch the file to sift-sink-agent --worker for sink judgment.

Designed for sift-server deployment (fnos / future cloud VPS) under systemd.
Stays alive, serial-dispatches sinks (one LLM call at a time to avoid rate
limits), logs to $SIFT_LOG_DIR/sift-sink-watcher.log.

Env:
  SIFT_JSONL_ROOT (default /vol1/1000/sift/jsonl)
  SIFT_LOG_DIR    (default /vol1/1000/sift/logs)
  SIFT_WATCH_SETTLE_SECONDS (default 10) — wait after close_write before reading
                                            (covers writer still flushing tail)
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
SINK_TIMEOUT = int(os.environ.get("SIFT_SINK_TIMEOUT", "300"))  # 5 min per sink


def log(msg: str):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [sink-watcher] {msg}\n")
    except Exception:
        pass


def process_jsonl(path: str):
    p = Path(path)
    if not p.exists() or not p.is_file():
        log(f"skip: not a file {path}")
        return
    time.sleep(SETTLE_SECONDS)
    if not p.exists():
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
    JSONL_ROOT.mkdir(parents=True, exist_ok=True)
    log(f"start watching {JSONL_ROOT} (settle={SETTLE_SECONDS}s, agent={SINK_AGENT})")
    cmd = [
        "inotifywait", "-m", "-r", "-e", "close_write",
        "--format", "%w%f", str(JSONL_ROOT),
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        log("ERROR: inotifywait not found (apt install inotify-tools)")
        sys.exit(2)

    for line in proc.stdout:
        path = line.strip()
        if not path.endswith(".jsonl"):
            continue
        log(f"close_write: {path}")
        process_jsonl(path)


if __name__ == "__main__":
    try:
        watch_loop()
    except KeyboardInterrupt:
        log("interrupted")
        sys.exit(0)
    except Exception as e:
        log(f"top-level: {e}")
        sys.exit(1)
