#!/usr/bin/env python3
"""auto-update-from-canonical skill: pull tooling updates from the canonical Sula source.

Aggregates SHA-256 of all 10 tooling files in tools/sula_vector/ both locally and
on canonical (https://raw.githubusercontent.com/irihiyahnj/sula-vector/main/...).
If aggregate hashes differ, clones the canonical repo to a temp dir and runs
migrate.py against this project (which idempotently refreshes tools/sula_vector/*
and the AGENTS.md sentinel block).

Emits a `kind: operation` fragment ONLY on actual update (Tier C7 — no churn
when already current; no fragment when network is unreachable).

Designed to be cron-friendly: silent on no-op, idempotent, exits 0 on
"already current" and "network unreachable" alike (so cron does not alarm
on transient connectivity).
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CANONICAL_RAW = (
    "https://raw.githubusercontent.com/irihiyahnj/sula-vector/main"
)
DEFAULT_CANONICAL_GIT = "https://github.com/irihiyahnj/sula-vector.git"

TOOLING_FILES = (
    "render.py",
    "AGENTS.md",
    "README.md",
    "RELEASE-NOTES.md",
    "principles/README.md",
    "skills/README.md",
    "skills/verifier-shell.py",
    "skills/scheduler.py",
    "skills/llm-dispatcher.py",
    "skills/auto-update-from-canonical.py",
)


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_local_hash(tools_dir: Path) -> str:
    h = hashlib.sha256()
    for rel in TOOLING_FILES:
        p = tools_dir / rel
        if p.exists():
            h.update(rel.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def aggregate_remote_hash(canonical_raw: str, timeout: int = 15) -> str | None:
    h = hashlib.sha256()
    for rel in TOOLING_FILES:
        url = f"{canonical_raw}/tools/sula_vector/{rel}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                content = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return None
        h.update(rel.encode("utf-8"))
        h.update(content)
    return h.hexdigest()


def hash_url(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return hashlib.sha256(resp.read()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_update_fragment(
    fragments_dir: Path,
    old_hash: str,
    new_hash: str,
    canonical_git: str,
    migrate_output: str,
) -> Path:
    ts = now_iso()
    safe_time = ts.replace(":", "-")
    fragment_id = f"{safe_time}--operation-auto-updated-from-canonical"
    target = fragments_dir / f"{fragment_id}.md"
    body = (
        f"Tooling auto-updated from canonical `{canonical_git}`.\n\n"
        f"aggregate hash: {old_hash[:12]} → {new_hash[:12]}\n\n"
        "migrate.py output:\n"
        "```\n"
        f"{migrate_output[:3000]}\n"
        "```\n"
    )
    target.write_text(
        "---\n"
        f"id: {fragment_id}\n"
        f"time: {ts}\n"
        "kind: operation\n"
        "tags: [auto-update, skill, canonical-pull]\n"
        f"old_aggregate_hash: {old_hash[:16]}\n"
        f"new_aggregate_hash: {new_hash[:16]}\n"
        f"canonical: {canonical_git}\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Auto-update this project's Sula tooling from the canonical source."
    )
    p.add_argument("--project-root", required=True)
    p.add_argument("--canonical-raw", default=DEFAULT_CANONICAL_RAW)
    p.add_argument("--canonical-git", default=DEFAULT_CANONICAL_GIT)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without modifying anything.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Print only on actual update or error (cron-friendly).",
    )
    args = p.parse_args(argv)

    root = Path(args.project_root).resolve()
    tools_dir = root / "tools" / "sula_vector"
    if not tools_dir.exists():
        print(f"local tools/sula_vector not found at {tools_dir}", file=sys.stderr)
        return 2

    local_hash = aggregate_local_hash(tools_dir)

    try:
        remote_hash = aggregate_remote_hash(args.canonical_raw)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        if not args.quiet:
            print(f"canonical unreachable ({exc}); skipping", file=sys.stderr)
        return 0

    if remote_hash is None:
        if not args.quiet:
            print(f"could not fetch one or more canonical files; skipping", file=sys.stderr)
        return 0

    if local_hash == remote_hash:
        if not args.quiet:
            print(f"[{root.name}] already current ({local_hash[:12]})")
        return 0

    print(f"[{root.name}] update available: {local_hash[:12]} → {remote_hash[:12]}")

    if args.dry_run:
        print(f"[{root.name}] dry-run: skipping refresh")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="sula-canonical-pull-"))
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", args.canonical_git, str(tmp / "canonical")],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        migrate_path = tmp / "canonical" / "tools" / "sula_vector" / "migrate.py"
        result = subprocess.run(
            ["python3", str(migrate_path), "--project-root", str(root)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[{root.name}] update failed: {exc.stderr}", file=sys.stderr)
        return 3
    except subprocess.TimeoutExpired:
        print(f"[{root.name}] update timed out", file=sys.stderr)
        return 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    new_hash = aggregate_local_hash(tools_dir)
    if new_hash != remote_hash:
        print(
            f"[{root.name}] refresh hash mismatch: got {new_hash[:12]}, expected {remote_hash[:12]}",
            file=sys.stderr,
        )
        return 3

    fragments_dir = root / "fragments"
    fragments_dir.mkdir(exist_ok=True)
    target = emit_update_fragment(
        fragments_dir, local_hash, new_hash, args.canonical_git, result.stdout
    )
    print(f"[{root.name}] updated to {new_hash[:12]} ({target.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
