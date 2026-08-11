#!/usr/bin/env python3
"""witness skill: mechanical capture of what actually changed.

Works on any substrate — a git repository, a Drive/Dropbox folder, a plain
folder of company documents. The previously witnessed state is not stored in
a state directory; it is folded out of the prior `kind: witness` fragments,
each of which records only its own delta. Truth stays in fragments (B2, B4).

    python3 witness.py --project-root .
    python3 witness.py --project-root . --label "季度提案定稿" --refs <decision-id>

Silent and non-appending when nothing changed (C7). Run it from a hook, a
cron, or by hand — the substrate schedules, Sula does not (B7).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render import load_fragments  # type: ignore

DEFAULT_IGNORE = [
    ".git",
    ".hg",
    ".svn",
    "fragments",
    ".sula",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".DS_Store",
    ".idea",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "~$*",
]

DOCUMENT_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".pages",
    ".numbers",
    ".key",
    ".odt",
    ".ods",
    ".odp",
    ".csv",
}

HASH_LIMIT_BYTES = 50 * 1024 * 1024
MAX_ARTIFACT_FRAGMENTS = 20


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ignore_patterns(frags: list, extra: list[str]) -> list[str]:
    patterns = list(DEFAULT_IGNORE)
    for f in frags:
        raw = f.get("witness_ignore")
        if not raw:
            continue
        items = raw if isinstance(raw, list) else str(raw).split(",")
        patterns.extend(str(i).strip() for i in items if str(i).strip())
    patterns.extend(extra)
    return patterns


def is_ignored(rel: Path, patterns: list[str]) -> bool:
    parts = rel.parts
    for pattern in patterns:
        if any(Path(part).match(pattern) for part in parts):
            return True
        if rel.match(pattern):
            return True
    return False


def hash_file(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size > HASH_LIMIT_BYTES:
        return f"s:{size}"
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return "unreadable"
    return digest.hexdigest()[:12]


def scan_tree(root: Path, patterns: list[str]) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if is_ignored(rel, patterns):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out[rel.as_posix()] = (hash_file(path), size)
    return out


def _encode_path(rel: str) -> str:
    """One file must be one line, or folding cannot round-trip.

    A newline in a filename is legal on every POSIX substrate and does occur in
    documents synced from other tools. Left raw it splits the delta line, the
    path folds back truncated, and the file is reported added and removed on
    every run forever. Only control characters are escaped, so CJK paths stay
    readable.
    """
    return rel.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")


def _decode_path(rel: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(rel):
        if rel[i] == "\\" and i + 1 < len(rel):
            nxt = rel[i + 1]
            if nxt in {"n", "r", "\\"}:
                out.append({"n": "\n", "r": "\r", "\\": "\\"}[nxt])
                i += 2
                continue
        out.append(rel[i])
        i += 1
    return "".join(out)


def fold_witnessed(frags: list) -> tuple[dict[str, tuple[str, int]], int]:
    """Replay every prior witness delta into the last known tree state."""
    state: dict[str, tuple[str, int]] = {}
    count = 0
    for f in frags:
        if f.kind != "witness":
            continue
        count += 1
        for line in f.body.splitlines():
            parts = line.split(None, 3)
            if len(parts) != 4 or parts[0] not in {"+", "~", "-"}:
                continue
            marker, digest, size, rel = parts
            rel = _decode_path(rel)
            if marker == "-":
                state.pop(rel, None)
            else:
                state[rel] = (digest, int(size) if size.isdigit() else 0)
    return state, count


def diff_tree(
    before: dict[str, tuple[str, int]], after: dict[str, tuple[str, int]]
) -> tuple[list[str], list[str], list[str]]:
    added = sorted(p for p in after if p not in before)
    removed = sorted(p for p in before if p not in after)
    changed = sorted(
        p for p in after if p in before and after[p][0] != before[p][0]
    )
    return added, changed, removed


def git_info(root: Path) -> dict[str, str]:
    if not (root / ".git").exists():
        return {}
    def run(*cmd: str) -> str:
        try:
            result = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    return {
        "commit": run("git", "rev-parse", "HEAD"),
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
    }


def git_commits_since(root: Path, since_commit: str) -> list[str]:
    if not (root / ".git").exists() or not since_commit:
        return []
    # `%x00` separates hash+subject from the file list so a commit that only
    # touched fragments/ (e.g. committing a previous witness) is dropped —
    # otherwise the post-commit hook would witness its own commits forever (C7).
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--no-decorate",
                "--name-only",
                "--format=%x00%h %s",
                f"{since_commit}..HEAD",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    out: list[str] = []
    for block in result.stdout.split("\x00"):
        block = block.strip("\n")
        if not block:
            continue
        header, _, files = block.partition("\n")
        paths = [p for p in files.splitlines() if p.strip()]
        if paths and all(p.startswith("fragments/") for p in paths):
            continue
        out.append(header.strip())
    return out


def last_witness_commit(frags: list) -> str:
    for f in reversed(frags):
        if f.kind == "witness" and f.get("commit"):
            return str(f.get("commit"))
    return ""


def tree_digest(tree: dict[str, tuple[str, int]]) -> str:
    digest = hashlib.sha256()
    for rel in sorted(tree):
        digest.update(rel.encode("utf-8"))
        digest.update(tree[rel][0].encode("utf-8"))
    return digest.hexdigest()[:12]


def write_witness(
    fragments_dir: Path,
    *,
    added: list[str],
    changed: list[str],
    removed: list[str],
    tree: dict[str, tuple[str, int]],
    label: str,
    refs: list[str],
    substrate: str,
    git: dict[str, str],
    commits: list[str],
    baseline: bool,
) -> Path:
    slug = "witness-baseline" if baseline else "witness"
    # Folding deltas requires a strict order, and same-second filenames sort by
    # slug rather than by creation order. One witness per second, at most.
    while True:
        stamp = now_iso()
        safe = stamp.replace(":", "-")
        target = fragments_dir / f"{safe}--{slug}.md"
        if not any(fragments_dir.glob(f"{safe}--witness*.md")):
            break
        time.sleep(0.25)

    headline = label or (
        f"Baseline of {len(tree)} file(s)."
        if baseline
        else f"+{len(added)} ~{len(changed)} -{len(removed)} file(s)."
    )
    lines = ["---", f"id: {target.stem}", f"time: {stamp}", "kind: witness"]
    if refs:
        lines.append(f"refs: [{', '.join(refs)}]")
    lines.append("tags: [witness, skill]")
    lines.append(f"summary: {headline}")
    lines.append(f"substrate: {substrate}")
    lines.append(f"files_added: {len(added)}")
    lines.append(f"files_changed: {len(changed)}")
    lines.append(f"files_removed: {len(removed)}")
    lines.append(f"tree_files: {len(tree)}")
    lines.append(f"tree_digest: {tree_digest(tree)}")
    if baseline:
        lines.append("baseline: true")
    for key, value in git.items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")

    body = [headline, ""]
    if commits:
        body.append("## commits")
        body.extend(f"  {c}" for c in commits)
        body.append("")
    body.append("## delta")
    for rel in added:
        digest, size = tree[rel]
        body.append(f"+ {digest} {size} {_encode_path(rel)}")
    for rel in changed:
        digest, size = tree[rel]
        body.append(f"~ {digest} {size} {_encode_path(rel)}")
    for rel in removed:
        body.append(f"- - - {_encode_path(rel)}")

    target.write_text("\n".join(lines + body) + "\n", encoding="utf-8")
    return target


def write_artifact(fragments_dir: Path, rel: str, witness_id: str) -> Path:
    stamp = now_iso()
    safe = stamp.replace(":", "-")
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:8]
    target = fragments_dir / f"{safe}--artifact-{digest}.md"
    suffix = 2
    while target.exists():
        target = fragments_dir / f"{safe}--artifact-{digest}-{suffix}.md"
        suffix += 1
    name = Path(rel).name
    target.write_text(
        "---\n"
        f"id: {target.stem}\n"
        f"time: {stamp}\n"
        "kind: artifact\n"
        f"refs: [{witness_id}]\n"
        "tags: [witness, skill]\n"
        f"summary: {name}\n"
        f"pointer: {rel}\n"
        "---\n"
        f"{name} appeared in the project. Witnessed mechanically; no claim about "
        "its content.\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Witness what changed in a project folder and append evidence."
    )
    p.add_argument("--project-root", required=True)
    p.add_argument("--label", default="", help="human/agent headline for this change")
    p.add_argument("--refs", nargs="*", default=[], help="ids this evidence supports")
    p.add_argument("--ignore", nargs="*", default=[], help="extra ignore patterns")
    p.add_argument(
        "--no-artifacts",
        action="store_true",
        help="do not emit a kind:artifact fragment per new document",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    root = Path(args.project_root).resolve()
    fragments_dir = root / "fragments"
    if not fragments_dir.is_dir():
        print(f"no fragments/ in {root}", file=sys.stderr)
        return 2

    frags = load_fragments(fragments_dir)
    unknown = [r for r in args.refs if r not in {f.id for f in frags}]
    if unknown:
        print(f"unknown fragment id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    patterns = ignore_patterns(frags, args.ignore)
    tree = scan_tree(root, patterns)
    before, witness_count = fold_witnessed(frags)
    added, changed, removed = diff_tree(before, tree)

    git = git_info(root)
    commits = git_commits_since(root, last_witness_commit(frags))
    substrate = "git" if git.get("commit") else "folder"
    baseline = witness_count == 0

    if not (added or changed or removed or commits):
        print("[witness] no change")
        return 0

    if args.dry_run:
        print(
            f"[witness] would append: +{len(added)} ~{len(changed)} "
            f"-{len(removed)} file(s), {len(commits)} new commit(s), "
            f"substrate={substrate}, baseline={baseline}"
        )
        for rel in (added + changed + removed)[:20]:
            print(f"    {rel}")
        return 0

    target = write_witness(
        fragments_dir,
        added=added,
        changed=changed,
        removed=removed,
        tree=tree,
        label=args.label,
        refs=list(args.refs),
        substrate=substrate,
        git=git,
        commits=commits,
        baseline=baseline,
    )
    print(
        f"[witness] + witness  {target.name}  "
        f"(+{len(added)} ~{len(changed)} -{len(removed)}, {len(commits)} commit(s))"
    )

    if args.no_artifacts:
        return 0

    documents = [
        rel for rel in added if Path(rel).suffix.lower() in DOCUMENT_SUFFIXES
    ]
    if not documents:
        return 0
    if len(documents) > MAX_ARTIFACT_FRAGMENTS:
        print(
            f"[witness] {len(documents)} new documents exceeds "
            f"{MAX_ARTIFACT_FRAGMENTS}; recorded in the witness delta only"
        )
        return 0
    for rel in documents:
        created = write_artifact(fragments_dir, rel, target.stem)
        print(f"[witness] + artifact  {created.name}  -> {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
