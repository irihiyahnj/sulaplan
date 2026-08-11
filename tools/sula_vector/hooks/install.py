#!/usr/bin/env python3
"""Install runtime capture for a Sula vector.

Capture must not depend on an agent remembering to write things down. This
installs whatever mechanical trigger the project's substrate already offers:

- git repository -> .git/hooks/post-commit (witness every commit)
- Kiro CLI       -> .kiro/agents/sula.json (agentSpawn injects the boot,
                    stop witnesses the turn) — written, never forced default
- Kiro IDE       -> .kiro/hooks/sula-witness.kiro.hook
- no git         -> launchd timer on macOS, else the cron line to paste

Two host formats exist because the CLI and the IDE do not read the same file.
The CLI reads a `hooks` field inside an agent configuration and knows the
triggers agentSpawn / userPromptSubmit / preToolUse / postToolUse / stop; it has
no agentStop and never reads .kiro/hooks/. Reporting an install that the host
ignores is worse than installing nothing, so each line below says which host it
actually reaches.

Idempotent. Existing non-Sula hooks are never overwritten; the Sula call is
appended to them instead.

    python3 tools/sula_vector/hooks/install.py --project-root .
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
from pathlib import Path

MARKER = "# sula-vector witness"
WITNESS = "tools/sula_vector/skills/witness.py"
BOOT = "tools/sula_vector/render.py"
INTERVAL_SECONDS = 900

POST_COMMIT = f"""#!/bin/sh
{MARKER}
python3 "$(git rev-parse --show-toplevel)/{WITNESS}" \\
  --project-root "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 || true
"""

CLI_AGENT = {
    "name": "sula",
    "description": (
        "Project agent with the Sula boot injected at spawn and mechanical "
        "capture at the end of every turn."
    ),
    "tools": ["*"],
    "hooks": {
        "agentSpawn": [
            {"command": f"python3 {BOOT} . --for-agent", "timeout_ms": 60000}
        ],
        "stop": [
            {"command": f"python3 {WITNESS} --project-root .", "timeout_ms": 60000}
        ],
    },
}

IDE_HOOK = {
    "name": "Sula witness",
    "version": "1.0.0",
    "description": "Append mechanical evidence of what changed at the end of every turn.",
    "when": {"type": "agentStop"},
    "then": {
        "type": "runCommand",
        "command": f"python3 {WITNESS} --project-root .",
    },
}

CRON_LINE = (
    "*/15 * * * * cd {root} && python3 " + WITNESS + " --project-root . "
    ">/dev/null 2>&1"
)


def _write_if_changed(target: Path, payload: str) -> bool:
    if target.exists() and target.read_text(encoding="utf-8") == payload:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")
    return True


def install_git_hook(root: Path) -> str:
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return "skipped: not a git repository"
    target = hooks_dir / "post-commit"
    if target.exists():
        text = target.read_text(encoding="utf-8")
        if MARKER in text:
            return "already installed: .git/hooks/post-commit"
        body = POST_COMMIT.split("\n", 1)[1]
        target.write_text(text.rstrip() + "\n\n" + body, encoding="utf-8")
        result = "appended to existing .git/hooks/post-commit"
    else:
        target.write_text(POST_COMMIT, encoding="utf-8")
        result = "installed: .git/hooks/post-commit"
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return result


def install_cli_agent(root: Path) -> str:
    target = root / ".kiro" / "agents" / "sula.json"
    payload = json.dumps(CLI_AGENT, indent=2, ensure_ascii=False) + "\n"
    written = _write_if_changed(target, payload)
    state = "installed" if written else "already installed"
    settings = root / ".kiro" / "settings" / "cli.json"
    active = False
    if settings.exists():
        try:
            active = json.loads(settings.read_text(encoding="utf-8")).get(
                "chat.defaultAgent"
            ) == "sula"
        except json.JSONDecodeError:
            active = False
    if active:
        return f"{state} and active: .kiro/agents/sula.json"
    return (
        f"{state} but NOT active: .kiro/agents/sula.json\n"
        "        activate with:  kiro-cli settings chat.defaultAgent sula\n"
        "        (not set for you: a custom agent replaces the built-in "
        "default agent's prompt)"
    )


def install_ide_hook(root: Path) -> str:
    target = root / ".kiro" / "hooks" / "sula-witness.kiro.hook"
    payload = json.dumps(IDE_HOOK, indent=2, ensure_ascii=False) + "\n"
    written = _write_if_changed(target, payload)
    state = "installed" if written else "already installed"
    return f"{state}: .kiro/hooks/sula-witness.kiro.hook (Kiro IDE only)"


def _launchd_label(root: Path) -> str:
    # The readable part is best-effort: a CJK-only folder name reduces to
    # nothing, and two such projects would then share one label and evict each
    # other. The path digest is what actually keeps labels distinct.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", root.name).strip("-").lower()
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    return f"com.sula-vector.witness.{slug}-{digest}" if slug else (
        f"com.sula-vector.witness.{digest}"
    )


def install_launchd(root: Path) -> str:
    label = _launchd_label(root)
    target = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    log = Path.home() / "Library" / "Logs" / f"{label}.log"
    payload = {
        "Label": label,
        "ProgramArguments": [sys.executable, str(root / WITNESS), "--project-root", str(root)],
        "WorkingDirectory": str(root),
        "StartInterval": INTERVAL_SECONDS,
        "RunAtLoad": False,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    encoded = plistlib.dumps(payload)
    if not (target.exists() and target.read_bytes() == encoded):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{label}"],
        capture_output=True,
        check=False,
    )
    done = subprocess.run(
        ["launchctl", "bootstrap", domain, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return (
            f"plist written but not loaded: {target}\n"
            f"        launchctl bootstrap said: {done.stderr.strip() or done.returncode}"
        )
    return f"loaded every {INTERVAL_SECONDS}s: {target}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Install mechanical capture triggers.")
    p.add_argument("--project-root", required=True)
    p.add_argument("--skip-git", action="store_true")
    p.add_argument("--skip-kiro", action="store_true")
    p.add_argument("--skip-schedule", action="store_true")
    args = p.parse_args(argv)

    root = Path(args.project_root).resolve()
    if not (root / "fragments").is_dir():
        print(f"no fragments/ in {root}")
        return 2

    print(f"[sula] installing capture for {root}")
    if not args.skip_git:
        print(f"  git       {install_git_hook(root)}")
    if not args.skip_kiro:
        print(f"  kiro-cli  {install_cli_agent(root)}")
        print(f"  kiro-ide  {install_ide_hook(root)}")
    if not (root / ".git").exists() and not args.skip_schedule:
        if sys.platform == "darwin":
            print(f"  launchd   {install_launchd(root)}")
        else:
            print("  schedule  no git substrate — paste this cron line:")
            print(f"            {CRON_LINE.format(root=root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
