#!/usr/bin/env python3
"""scheduler skill: fire cadence-tick fragments when a recurring intent's interval has elapsed.

Reads fragments where kind=intent and cadence is set (e.g. cadence: every-30m,
cadence: every-2h, cadence: daily). For each such intent, finds the most
recent cadence-tick (a kind:cadence-tick fragment whose refs include the
intent's id), or falls back to the intent's own time. If the cadence
interval has elapsed since then, appends a fresh kind:cadence-tick fragment
with refs back to the intent.

Idempotent: running twice within the cadence window appends nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render import load_fragments  # type: ignore

CADENCE_RE = re.compile(r"^every-(\d+)([mhd])$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_cadence(spec: str) -> timedelta | None:
    spec = spec.strip().lower()
    if spec == "daily":
        return timedelta(days=1)
    if spec == "hourly":
        return timedelta(hours=1)
    m = CADENCE_RE.match(spec)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    return None


def emit_tick(fragments_dir: Path, intent_id: str, intent_body: str) -> Path:
    ts = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_time = ts.replace(":", "-")
    slug = f"cadence-tick-{intent_id[:80]}"
    fragment_id = f"{safe_time}--{slug}"
    target = fragments_dir / f"{fragment_id}.md"
    body_preview = (intent_body or "").strip().split("\n", 1)[0][:160]
    body = f"Cadence tick for {intent_id}.\n\n{body_preview}"
    target.write_text(
        "---\n"
        f"id: {fragment_id}\n"
        f"time: {ts}\n"
        "kind: cadence-tick\n"
        f"refs: [{intent_id}]\n"
        "tags: [skill, scheduler]\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fire cadence-tick fragments for due recurring intents.")
    p.add_argument("--project-root", required=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List due intents without appending tick fragments.",
    )
    args = p.parse_args(argv)

    root = Path(args.project_root).resolve()
    fragments_dir = root / "fragments"
    if not fragments_dir.is_dir():
        print(f"no fragments/ in {root}", file=sys.stderr)
        return 2

    frags = load_fragments(fragments_dir)
    recurring = [
        f
        for f in frags
        if f.kind == "intent" and isinstance(f.get("cadence"), str)
    ]

    if not recurring:
        print("no recurring intents found")
        return 0

    fired = 0
    skipped = 0
    now = now_utc()

    for intent in recurring:
        cadence = parse_cadence(str(intent.get("cadence")))
        if cadence is None:
            print(f"[scheduler] {intent.id}: bad cadence '{intent.get('cadence')}', skipping")
            continue
        ticks = [
            f
            for f in frags
            if f.kind == "cadence-tick" and intent.id in f.refs
        ]
        last = max(
            [parse_iso(t.time) for t in ticks if parse_iso(t.time)] + [parse_iso(intent.time)],
            default=None,
        )
        if last is None:
            print(f"[scheduler] {intent.id}: cannot parse time, skipping")
            continue
        elapsed = now - last
        due = elapsed >= cadence
        status = "DUE" if due else f"in {cadence - elapsed}"
        print(f"[scheduler] {intent.id} cadence={intent.get('cadence')}: {status}")
        if due and not args.dry_run:
            emit_tick(fragments_dir, intent.id, intent.body)
            fired += 1
        elif due and args.dry_run:
            fired += 1
        else:
            skipped += 1

    print(f"[scheduler] fired={fired} skipped={skipped} (dry-run={args.dry_run})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
