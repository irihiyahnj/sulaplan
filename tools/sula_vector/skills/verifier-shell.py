#!/usr/bin/env python3
"""verifier-shell skill: run shell commands as goal verifiers.

Reads fragments where kind=goal and verifier_ref starts with `shell:`.
For any such goal not yet satisfied, runs the shell command in the
project root and appends a kind: verification-fact fragment with
passed: true/false and the command output.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render import _is_satisfied, load_fragments  # type: ignore

DEFAULT_TIMEOUT_SECONDS = 600
OUTPUT_TRUNCATE = 4000


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_command(command: str, cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"verifier timed out after {timeout}s"
    output = (result.stdout + result.stderr).strip()
    if len(output) > OUTPUT_TRUNCATE:
        output = output[:OUTPUT_TRUNCATE] + "\n…(truncated)"
    return result.returncode == 0, output


def write_verification_fact(
    fragments_dir: Path, goal_id: str, command: str, passed: bool, output: str
) -> Path:
    ts = now_iso()
    safe_time = ts.replace(":", "-")
    base_slug = f"verification-fact-shell-{goal_id[:60]}"
    fragment_id = f"{safe_time}--{base_slug}"
    target = fragments_dir / f"{fragment_id}.md"
    body = f"shell verifier: `{command}`\n\n```\n{output}\n```"
    target.write_text(
        "---\n"
        f"id: {fragment_id}\n"
        f"time: {ts}\n"
        "kind: verification-fact\n"
        f"refs: [{goal_id}]\n"
        f"passed: {'true' if passed else 'false'}\n"
        "tags: [skill, verifier-shell]\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Run shell-command verifiers for Sula vector goals."
    )
    p.add_argument("--project-root", required=True)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List goals that would be evaluated without running commands.",
    )
    args = p.parse_args(argv)

    root = Path(args.project_root).resolve()
    fragments_dir = root / "fragments"
    if not fragments_dir.is_dir():
        print(f"no fragments/ in {root}", file=sys.stderr)
        return 2

    frags = load_fragments(fragments_dir)
    candidates = [
        f
        for f in frags
        if f.kind == "goal"
        and isinstance(f.get("verifier_ref"), str)
        and str(f.get("verifier_ref", "")).startswith("shell:")
        and not _is_satisfied(f, frags)
    ]

    if not candidates:
        print("no shell-verified goals to evaluate")
        return 0

    for goal in candidates:
        verifier_ref = str(goal.get("verifier_ref", ""))
        command = verifier_ref[len("shell:") :].strip()
        if not command:
            continue
        print(f"[verifier-shell] {goal.id}: {command}")
        if args.dry_run:
            continue
        passed, output = run_command(command, root, args.timeout)
        target = write_verification_fact(
            fragments_dir, goal.id, command, passed, output
        )
        status = "PASS" if passed else "FAIL"
        print(f"[verifier-shell] -> {status}  {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
