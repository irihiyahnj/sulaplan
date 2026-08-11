#!/usr/bin/env python3
"""Sula vector renderer.

Pure function from a folder of typed text fragments to a project view.
Standard library only. See ../../docs/sula-vector-convention.md for the spec.

Identity is derived from the filename, never from hand-written frontmatter:
a fragment cannot carry a wrong id or a wrong timestamp, and no fragment is
ever silently dropped. Structural problems surface through `--view doctor`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CONVENTION_VERSION = "1.1"

TIER_ORDER = ["highest", "invariant", "aesthetic", "discipline", "anti-pattern"]
PROJECT_TIER = "project"
PRINCIPLE_ORDER = TIER_ORDER + [PROJECT_TIER]
TIER_TITLES = {
    "highest": "Tier A — Highest rule",
    "invariant": "Tier B — Invariants",
    "aesthetic": "Tier C — Aesthetics",
    "discipline": "Tier D — Implementation discipline",
    "anti-pattern": "Tier E — Anti-patterns",
    PROJECT_TIER: "Project principles",
}

LANES = ("evidence", "judgment", "direction")
LANE_TITLES = {
    "evidence": "Position — what happened",
    "judgment": "Direction — judgments in force",
    "direction": "Heading — open directions",
}
LANE_BY_KIND = {
    "decision": "judgment",
    "correction": "judgment",
    "principle": "judgment",
    "assessment": "judgment",
    "annotation": "judgment",
    "preference": "judgment",
    "pitfall": "judgment",
    "chronicle": "judgment",
    "skill": "judgment",
    "intent": "direction",
    "goal": "direction",
}

FILENAME_TIME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})Z(?:--(.*))?$"
)
FRONTMATTER_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass
class Fragment:
    id: str
    time: str
    kind: str
    refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    path: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        if key in {"id", "time", "kind", "refs", "tags", "body", "path"}:
            return getattr(self, key)
        return self.extra.get(key, default)

    def id_list(self, key: str) -> list[str]:
        raw = self.get(key)
        if raw is None or raw == "":
            return []
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [str(raw).strip()]


@dataclass
class Problem:
    code: str
    fragment: str
    path: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "fragment": self.fragment,
            "path": self.path,
            "detail": self.detail,
        }


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    return value


def _parse_inline_list(value: str) -> list[Any]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(item) for item in inner.split(",")]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        tail = text.find("\n---", 4)
        if tail == -1 or text[tail:].strip() != "---":
            return {}, text
        end = tail
        body = ""
    else:
        body = text[end + 5 :]
    raw = text[4:end]

    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_list_key is not None:
            out[current_list_key].append(_parse_scalar(line[4:]))
            continue
        if ":" not in line:
            current_list_key = None
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            out[key] = []
            current_list_key = key
        elif value.startswith("[") and value.endswith("]"):
            out[key] = _parse_inline_list(value)
            current_list_key = None
        else:
            out[key] = _parse_scalar(value)
            current_list_key = None
    return out, body.strip()


def derive_identity(path: Path) -> tuple[str, str | None]:
    """Fragment id and time as derived from the filename. Filename is truth."""
    stem = path.stem
    match = FILENAME_TIME_RE.match(stem)
    if not match:
        return stem, None
    day, hh, mm, ss, _slug = match.groups()
    return stem, f"{day}T{hh}:{mm}:{ss}Z"


def load_report(folder: Path) -> tuple[list[Fragment], list[Problem]]:
    """Load every fragment file. Nothing is ever skipped silently."""
    frags: list[Fragment] = []
    problems: list[Problem] = []
    for path in sorted(folder.rglob("*.md")):
        if path.name in {"AGENTS.md", "README.md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(Problem("unreadable", path.stem, str(path), str(exc)))
            continue

        meta, body = _parse_frontmatter(text)
        fid, derived_time = derive_identity(path)

        if not meta:
            problems.append(
                Problem("no-frontmatter", fid, str(path), "no `---` header block")
            )

        declared_time = str(meta.get("time", "")).strip()
        time = derived_time or declared_time
        if derived_time is None:
            problems.append(
                Problem(
                    "unparsable-filename",
                    fid,
                    str(path),
                    "filename must start with <YYYY-MM-DDTHH-MM-SSZ>--",
                )
            )
            if declared_time and not FRONTMATTER_TIME_RE.match(declared_time):
                problems.append(
                    Problem("unparsable-time", fid, str(path), declared_time)
                )
                time = ""
        elif declared_time and declared_time != derived_time:
            problems.append(
                Problem(
                    "header-disagreement",
                    fid,
                    str(path),
                    f"frontmatter time {declared_time} != filename time {derived_time}",
                )
            )

        declared_id = str(meta.get("id", "")).strip()
        if declared_id and declared_id != fid:
            problems.append(
                Problem(
                    "header-disagreement",
                    fid,
                    str(path),
                    f"frontmatter id {declared_id} != filename stem {fid}",
                )
            )

        kind = str(meta.get("kind", "")).strip()
        if not kind:
            problems.append(
                Problem("missing-kind", fid, str(path), "`kind` is required")
            )
            kind = "unknown"

        refs = meta.get("refs") or []
        tags = meta.get("tags") or []
        extra = {
            k: v
            for k, v in meta.items()
            if k not in {"id", "time", "kind", "refs", "tags"}
        }
        frags.append(
            Fragment(
                id=fid,
                time=time,
                kind=kind,
                refs=[str(x) for x in refs],
                tags=[str(x) for x in tags],
                extra=extra,
                body=body,
                path=str(path),
            )
        )

    frags.sort(key=lambda f: (f.time, f.id))
    return frags, problems


def load_fragments(folder: Path) -> list[Fragment]:
    return load_report(folder)[0]


def lane_of(f: Fragment) -> str:
    declared = str(f.get("lane", "")).strip()
    if declared in LANES:
        return declared
    return LANE_BY_KIND.get(f.kind, "evidence")


def _matches(
    f: Fragment,
    *,
    kind: str | None = None,
    since: str | None = None,
    until: str | None = None,
    tag: str | None = None,
    ref: str | None = None,
    thread: str | None = None,
    family: str | None = None,
    lane: str | None = None,
) -> bool:
    if kind and f.kind != kind:
        return False
    if since and f.time < since:
        return False
    if until and f.time > until:
        return False
    if tag and tag not in f.tags:
        return False
    if ref and ref not in f.refs:
        return False
    if thread and f.get("thread_id") != thread:
        return False
    if family and f.get("family_key") != family:
        return False
    if lane and lane_of(f) != lane:
        return False
    return True


def filter_fragments(frags: Iterable[Fragment], **q: Any) -> list[Fragment]:
    return [f for f in frags if _matches(f, **q)]


def _summarize(f: Fragment, max_chars: int = 200) -> str:
    declared = str(f.get("summary", "")).strip()
    text = declared or " ".join(
        line.strip()
        for line in f.body.strip().split("\n\n", 1)[0].splitlines()
        if line.strip()
    )
    text = text.lstrip("# ").strip()
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    for stop in ("。", ". ", "；", "; ", "，", ", ", " "):
        cut = window.rfind(stop)
        if cut > max_chars // 2:
            return window[: cut + (1 if stop in "。；，" else 0)].strip() + "…"
    return window.strip() + "…"


def _to_dict(f: Fragment) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f.id,
        "time": f.time,
        "kind": f.kind,
        "lane": lane_of(f),
        "refs": f.refs,
        "tags": f.tags,
    }
    base.update(f.extra)
    base["summary"] = _summarize(f)
    base["path"] = f.path
    return base


def supersession_map(frags: Iterable[Fragment]) -> dict[str, list[str]]:
    """id -> ids of later fragments that explicitly supersede it."""
    out: dict[str, list[str]] = {}
    for f in frags:
        for target in f.id_list("supersedes"):
            if target != f.id:
                out.setdefault(target, []).append(f.id)
    return out


def closure_map(frags: Iterable[Fragment]) -> dict[str, list[str]]:
    """id -> ids of fragments that declare it closed."""
    out: dict[str, list[str]] = {}
    for f in frags:
        for target in f.id_list("closes"):
            if target != f.id:
                out.setdefault(target, []).append(f.id)
    return out


def _is_satisfied(intent: Fragment, frags: list[Fragment]) -> bool:
    if closure_map(frags).get(intent.id):
        return True
    back_refs = [f for f in frags if intent.id in f.refs]
    if intent.kind == "goal":
        return any(
            f.kind == "verification-fact" and f.get("passed") in {True, "true"}
            for f in back_refs
        )
    if "done_when" in intent.extra:
        return any(f.kind in {"fact", "verification-fact"} for f in back_refs)
    return False


def _pinned_threads(frags: list[Fragment]) -> list[dict[str, Any]]:
    threads: dict[str, list[Fragment]] = {}
    pinned_ids: set[str] = set()
    for f in frags:
        tid = f.get("thread_id")
        if not tid:
            continue
        threads.setdefault(str(tid), []).append(f)
        if f.get("pinned") in {True, "true"}:
            pinned_ids.add(str(tid))
    out = []
    for tid in sorted(pinned_ids):
        items = sorted(threads[tid], key=lambda f: f.time)
        last = items[-1]
        out.append(
            {
                "thread_id": tid,
                "last_turn_time": last.time,
                "last_turn_summary": _summarize(last),
                "turn_count": len(items),
            }
        )
    return out


def view_list(frags: list[Fragment]) -> list[dict[str, Any]]:
    return [_to_dict(f) for f in frags]


def _int_field(f: Fragment, key: str) -> int:
    try:
        return int(str(f.get(key, 0) or 0))
    except ValueError:
        return 0


def _witnessed_change(f: Fragment) -> bool:
    return f.get("baseline") not in {True, "true"} and any(
        _int_field(f, k) for k in ("files_added", "files_changed", "files_removed")
    )


def judgment_gap(frags: list[Fragment]) -> list[Fragment]:
    """Witnessed change that nothing deliberate accounts for (B8/E8).

    Mechanical capture proves work happened; only a judgment or a direction says
    why. Evidence is the one lane a machine can write, so evidence alone leaves
    the why nowhere.

    The unit is the window between two captures, not the instant: a capture hook
    fires at the end of a turn, so the judgment that explains a change is
    normally written *before* the witness that records it. Comparing timestamps
    would flag every well-behaved turn, and a notice that cries wolf is worse
    than no notice.

    Never an error: forcing an append would buy E8 with C7.
    """
    deliberate = [
        f.time for f in frags if lane_of(f) in {"judgment", "direction"}
    ]
    gap: list[Fragment] = []
    previous_capture = ""
    for f in frags:
        if f.kind != "witness":
            continue
        if _witnessed_change(f) and not any(t > previous_capture for t in deliberate):
            gap.append(f)
        previous_capture = f.time
    return gap


def view_digest(frags: list[Fragment], n: int = 10) -> dict[str, Any]:
    # Each lane ends by its own semantics: a judgment ends when superseded, a
    # direction when closed, evidence only recedes into the past. Capping the
    # first two by recency drops live state with no fragment recording it (B2).
    superseded = supersession_map(frags)
    decisions = [
        f
        for f in frags
        if lane_of(f) == "judgment"
        and f.kind != "principle"
        and f.id not in superseded
    ]
    open_intents = [
        f
        for f in frags
        if lane_of(f) == "direction" and not _is_satisfied(f, frags)
    ]
    recent = [f for f in frags if lane_of(f) == "evidence"][-n:]
    return {
        "decisions": [_to_dict(f) for f in decisions],
        "open_intents": [_to_dict(f) for f in open_intents],
        "recent": [_to_dict(f) for f in recent],
        "pinned_threads": _pinned_threads(frags),
    }


def view_progress(frags: list[Fragment]) -> list[dict[str, Any]]:
    intents = [
        f
        for f in frags
        if f.kind in {"intent", "goal"} and "done_when" in f.extra
    ]
    out = []
    for it in intents:
        evidence = [
            f
            for f in frags
            if it.id in f.refs and f.kind in {"fact", "verification-fact"}
        ]
        out.append(
            {
                "intent": _to_dict(it),
                "evidence": [_to_dict(f) for f in evidence],
                "met": _is_satisfied(it, frags),
            }
        )
    return out


def view_thread(frags: list[Fragment], thread_id: str) -> list[dict[str, Any]]:
    return [_to_dict(f) for f in frags if f.get("thread_id") == thread_id]


def view_family(frags: list[Fragment], family_key: str) -> dict[str, Any]:
    members = [f for f in frags if f.get("family_key") == family_key]
    by_role: dict[str, Fragment] = {}
    for f in members:
        role = str(f.get("artifact_role", "default"))
        if role not in by_role or f.time > by_role[role].time:
            by_role[role] = f
    return {
        "family_key": family_key,
        "members": [_to_dict(f) for f in members],
        "latest_by_role": {r: _to_dict(f) for r, f in by_role.items()},
    }


def view_goals(frags: list[Fragment]) -> list[dict[str, Any]]:
    goals = [f for f in frags if f.kind == "goal"]
    out = []
    for g in goals:
        verifications = [
            f for f in frags if g.id in f.refs and f.kind == "verification-fact"
        ]
        out.append(
            {
                "goal": _to_dict(g),
                "verifications": [_to_dict(f) for f in verifications],
                "met": _is_satisfied(g, frags),
            }
        )
    return out


def view_principles(frags: list[Fragment]) -> dict[str, list[dict[str, Any]]]:
    # `tier` groups principles, it never filters them. A project's own
    # principles carry no Tier A–E label, and dropping them made the most
    # load-bearing judgment in a real project invisible in every view.
    grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in PRINCIPLE_ORDER}
    superseded = supersession_map(frags)
    for f in frags:
        if f.kind != "principle" or f.id in superseded:
            continue
        tier = str(f.get("tier", "")).strip()
        entry = _to_dict(f)
        entry["body"] = f.body
        grouped[tier if tier in grouped else PROJECT_TIER].append(entry)
    return grouped


def view_effective(frags: list[Fragment]) -> dict[str, Any]:
    """Judgments in force, with the supersession trail attached."""
    superseded = supersession_map(frags)
    by_id = {f.id: f for f in frags}
    in_force: list[dict[str, Any]] = []
    retired: list[dict[str, Any]] = []
    for f in frags:
        if lane_of(f) != "judgment":
            continue
        entry = _to_dict(f)
        if f.id in superseded:
            entry["superseded_by"] = [
                {
                    "id": sid,
                    "time": by_id[sid].time if sid in by_id else "",
                    "summary": _summarize(by_id[sid]) if sid in by_id else "",
                }
                for sid in superseded[f.id]
            ]
            retired.append(entry)
        else:
            in_force.append(entry)
    return {"in_force": in_force, "retired": retired}


def view_journal(frags: list[Fragment]) -> list[dict[str, Any]]:
    """Day-by-day project journal: what was decided, what was produced."""
    days: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for f in frags:
        if f.kind == "principle":
            continue
        day = f.time[:10] or "unknown"
        bucket = days.setdefault(day, {lane: [] for lane in LANES})
        entry = _to_dict(f)
        bucket[lane_of(f)].append(entry)
    return [
        {
            "day": day,
            "judgment": days[day]["judgment"],
            "evidence": days[day]["evidence"],
            "direction": days[day]["direction"],
        }
        for day in sorted(days)
    ]


def view_doctor(frags: list[Fragment], problems: list[Problem]) -> dict[str, Any]:
    """Structural integrity of the vector. Pure function, no side effects."""
    found = [p.as_dict() for p in problems]
    ids = {f.id for f in frags}

    seen: dict[str, str] = {}
    for f in frags:
        if f.id in seen:
            found.append(
                Problem("duplicate-id", f.id, f.path, f"also at {seen[f.id]}").as_dict()
            )
        seen[f.id] = f.path

    acknowledged = {
        str(f.get("broken_ref", "")).strip()
        for f in frags
        if str(f.get("broken_ref", "")).strip()
    }
    for f in frags:
        for target in f.refs + f.id_list("supersedes") + f.id_list("closes"):
            if ":" in target and not target.startswith("20"):
                continue
            if target in ids or target in acknowledged:
                continue
            found.append(
                Problem("dangling-ref", f.id, f.path, f"-> {target}").as_dict()
            )

    for f in frags:
        if f.kind == "goal" and not str(f.get("verifier_ref", "")).strip():
            found.append(
                Problem("goal-without-verifier", f.id, f.path, "B9/E9").as_dict()
            )

    by_code: dict[str, int] = {}
    for p in found:
        by_code[p["code"]] = by_code.get(p["code"], 0) + 1
    return {
        "fragments": len(frags),
        "problems": found,
        "by_code": dict(sorted(by_code.items(), key=lambda x: (-x[1], x[0]))),
        "ok": not found,
    }


def view_changes_summary(frags: list[Fragment]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    fragment_entries: list[dict[str, Any]] = []
    for f in frags:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        entry: dict[str, Any] = {
            "id": f.id,
            "time": f.time,
            "kind": f.kind,
            "lane": lane_of(f),
            "summary": _summarize(f, max_chars=120),
            "refs": list(f.refs),
        }
        if f.kind == "verification-fact":
            entry["passed"] = f.get("passed") in {True, "true"}
        fragment_entries.append(entry)
    return {
        "total": len(frags),
        "by_kind": dict(sorted(by_kind.items(), key=lambda x: (-x[1], x[0]))),
        "fragments": fragment_entries,
    }


def render_changes_summary_line(summary: dict[str, Any]) -> str:
    if summary["total"] == 0:
        return "[sula] no changes"
    parts = ", ".join(f"{n} {k}" for k, n in summary["by_kind"].items())
    return f"[sula] +{summary['total']} ({parts})"


def render_changes_summary_block(frags: list[Fragment]) -> str:
    if not frags:
        return "[sula] no changes"
    width = max((len(f.kind) for f in frags), default=4)
    width = max(width, len("verification-fact"))
    lines = [f"[sula] +{len(frags)} this turn:"]
    for f in frags:
        marker = "+"
        summary = _summarize(f, max_chars=120)
        if f.kind == "verification-fact":
            passed = f.get("passed") in {True, "true"}
            marker = "✓" if passed else "✗"
            target = f.refs[0] if f.refs else ""
            short_target = target.split("--", 1)[-1] if "--" in target else target
            status = "PASS" if passed else "FAIL"
            summary = f"{status}  {short_target}"
        lines.append(f"  {marker} {f.kind.ljust(width)}  {summary}")
    gap = judgment_gap(frags)
    if gap:
        changed = sum(
            _int_field(f, k)
            for f in gap
            for k in ("files_added", "files_changed", "files_removed")
        )
        lines.append("")
        lines.append(
            f"  ! {changed} file change(s) witnessed, no judgment recorded — "
            "why is not in the vector (B8/E8)"
        )
    return "\n".join(lines)


def render_principles_block(frags: list[Fragment]) -> str:
    grouped = view_principles(frags)
    if not any(grouped.values()):
        return (
            "## Principles in force\n\n"
            "(no principle fragments found in this vector — copy "
            "tools/sula_vector/principles/*.md into fragments/)\n"
        )
    lines: list[str] = ["## Principles in force", ""]
    for tier in PRINCIPLE_ORDER:
        items = grouped[tier]
        if not items:
            continue
        lines.append(f"### {TIER_TITLES[tier]}")
        lines.append("")
        for p in items:
            body = (p.get("body") or "").strip()
            if body:
                lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_doctor_block(report: dict[str, Any]) -> str:
    if report["ok"]:
        return f"[sula] doctor OK — {report['fragments']} fragments, 0 problems\n"
    lines = [
        f"[sula] doctor found {len(report['problems'])} problem(s) "
        f"in {report['fragments']} fragments:"
    ]
    for code, count in report["by_code"].items():
        lines.append(f"  {count:4d}  {code}")
    lines.append("")
    for p in report["problems"]:
        lines.append(f"  {p['code']}: {p['fragment']}")
        if p["detail"]:
            lines.append(f"      {p['detail']}")
    return "\n".join(lines) + "\n"


def render_for_agent(
    frags: list[Fragment], project_name: str = "", n: int = 10
) -> str:
    non_principle = [f for f in frags if f.kind != "principle"]
    digest = view_digest(non_principle, n=n)
    superseded = supersession_map(non_principle)
    lines: list[str] = []
    header = (
        f"# {project_name} (Sula vector)"
        if project_name
        else "# Project context (Sula vector)"
    )
    lines.append(header)
    lines.append("")
    lines.append(f"Convention: v{CONVENTION_VERSION}")
    latest = non_principle[-1].time if non_principle else "n/a"
    lines.append(
        f"Fragments: {len(non_principle)} activity, "
        f"{len(frags) - len(non_principle)} principle, "
        f"latest activity at {latest}"
    )
    lines.append("")

    lines.append(render_principles_block(frags).rstrip())
    lines.append("")

    if digest["pinned_threads"]:
        lines.append("## Pinned threads (last turn)")
        for t in digest["pinned_threads"]:
            lines.append(
                f"- {t['thread_id']} [{t['last_turn_time']}]: {t['last_turn_summary']}"
            )
        lines.append("")

    retired = sum(1 for f in non_principle if f.id in superseded)
    lines.append(f"## {LANE_TITLES['judgment']}")
    if not digest["decisions"]:
        lines.append("- (none)")
    for d in digest["decisions"]:
        lines.append(f"- [{d['time']}] {d['kind']} {d['id']}: {d['summary']}")
    if retired:
        lines.append(
            f"- ({retired} superseded judgment(s) hidden — `--view effective` to see the trail)"
        )
    lines.append("")

    lines.append(f"## {LANE_TITLES['direction']}")
    if not digest["open_intents"]:
        lines.append("- (none)")
    for i in digest["open_intents"]:
        lines.append(f"- [{i['time']}] {i['kind']} {i['id']}: {i['summary']}")
    lines.append("")

    lines.append(f"## {LANE_TITLES['evidence']}")
    if not digest["recent"]:
        lines.append("- (none)")
    for r in digest["recent"]:
        lines.append(f"- [{r['time']}] {r['kind']}: {r['summary']}")
    lines.append("")

    gap = judgment_gap(non_principle)
    if gap:
        lines.append("## Unexplained change")
        for f in gap:
            lines.append(
                f"- [{f.time}] {f.id}: {_summarize(f, max_chars=120)}"
            )
        lines.append(
            "- No judgment follows this change. Whoever knows why should append "
            "one; it cannot be recovered from the files."
        )
        lines.append("")

    lines.append("## How to act")
    lines.append(
        "Append one new fragment per judgment. Never edit past fragments. "
        "Use `note.py` so id and time are machine-derived:"
    )
    lines.append("")
    lines.append(
        '    python3 tools/sula_vector/note.py . --kind decision "<what and why>"'
    )
    lines.append("")
    lines.append(
        "Mechanical evidence (files produced, commits made) is captured by "
        "`skills/witness.py`; you do not need to describe it by hand. "
        "Supersede a past judgment with `--supersedes <id>`; close an open "
        "direction with `--closes <id>`."
    )
    return "\n".join(lines).rstrip() + "\n"


def _format_human(view: str, result: Any, out: Any) -> None:
    if view == "digest":
        for section in ("pinned_threads", "decisions", "open_intents", "recent"):
            out.write(f"## {section}\n")
            items = result.get(section, [])
            if not items:
                out.write("(none)\n\n")
                continue
            for it in items:
                if section == "pinned_threads":
                    out.write(
                        f"- {it['thread_id']} [{it['last_turn_time']}]: "
                        f"{it['last_turn_summary']}\n"
                    )
                else:
                    out.write(
                        f"- [{it['time']}] {it.get('kind','?')} "
                        f"{it.get('id','')}: {it.get('summary','')}\n"
                    )
            out.write("\n")
        return
    if view == "progress":
        for row in result:
            it = row["intent"]
            mark = "✓" if row["met"] else "·"
            out.write(
                f"{mark} [{it['time']}] {it['kind']} {it['id']}: "
                f"{it.get('summary','')}\n"
            )
            for ev in row["evidence"]:
                out.write(
                    f"    └ [{ev['time']}] {ev['kind']}: {ev.get('summary','')}\n"
                )
        return
    if view == "goals":
        for row in result:
            g = row["goal"]
            mark = "✓" if row["met"] else "·"
            out.write(f"{mark} {g['id']}: {g.get('summary','')}\n")
            for v in row["verifications"]:
                passed = v.get("passed") in {True, "true"}
                out.write(
                    f"    {'PASS' if passed else 'FAIL'} [{v['time']}]: "
                    f"{v.get('summary','')}\n"
                )
        return
    if view == "family":
        out.write(f"family: {result['family_key']}\n")
        for role, item in result["latest_by_role"].items():
            out.write(
                f"  {role}: [{item['time']}] {item['id']} -> "
                f"{item.get('pointer','-')}\n"
            )
        return
    if view == "effective":
        out.write(f"## in force ({len(result['in_force'])})\n")
        for it in result["in_force"]:
            out.write(f"- [{it['time']}] {it['kind']}: {it.get('summary','')}\n")
        out.write(f"\n## retired ({len(result['retired'])})\n")
        for it in result["retired"]:
            out.write(f"- [{it['time']}] {it['kind']}: {it.get('summary','')}\n")
            for s in it.get("superseded_by", []):
                out.write(f"    ↳ superseded by [{s['time']}] {s['summary']}\n")
        return
    if view == "journal":
        for day in result:
            out.write(f"## {day['day']}\n")
            for it in day["judgment"]:
                out.write(f"  ◆ {it['kind']}: {it.get('summary','')}\n")
            for it in day["direction"]:
                out.write(f"  → {it['kind']}: {it.get('summary','')}\n")
            for it in day["evidence"]:
                pointer = it.get("pointer")
                tail = f"  [{pointer}]" if pointer else ""
                out.write(f"  · {it['kind']}: {it.get('summary','')}{tail}\n")
            out.write("\n")
        return
    for it in result:
        out.write(
            f"[{it['time']}] {it.get('kind','?')} {it.get('id','')}: "
            f"{it.get('summary','')}\n"
        )


VIEWS = [
    "digest",
    "list",
    "progress",
    "thread",
    "family",
    "goals",
    "principles",
    "changes-summary",
    "effective",
    "journal",
    "doctor",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render a Sula vector folder.")
    p.add_argument("folder", help="path to a folder containing fragments/")
    p.add_argument("--view", default="digest", choices=VIEWS)
    p.add_argument("--kind")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--tag")
    p.add_argument("--ref")
    p.add_argument("--thread")
    p.add_argument("--family")
    p.add_argument("--lane", choices=LANES)
    p.add_argument("--for-agent", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--project-name", default="")
    args = p.parse_args(argv)

    root = Path(args.folder)
    fragments_dir = root / "fragments" if (root / "fragments").is_dir() else root
    if not fragments_dir.exists():
        print(f"folder not found: {fragments_dir}", file=sys.stderr)
        return 2

    frags, problems = load_report(fragments_dir)
    filtered = filter_fragments(
        frags,
        kind=args.kind,
        since=args.since,
        until=args.until,
        tag=args.tag,
        ref=args.ref,
        thread=args.thread,
        family=args.family,
        lane=args.lane,
    )

    if args.for_agent:
        sys.stdout.write(render_for_agent(filtered, args.project_name))
        return 0

    if args.view == "doctor":
        report = view_doctor(frags, problems)
        if args.json:
            json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(render_doctor_block(report))
        return 0 if report["ok"] else 1

    if args.view == "digest":
        result: Any = view_digest(filtered)
    elif args.view == "list":
        result = view_list(filtered)
    elif args.view == "progress":
        result = view_progress(filtered)
    elif args.view == "thread":
        if not args.thread:
            print("--thread is required for view=thread", file=sys.stderr)
            return 2
        result = view_thread(filtered, args.thread)
    elif args.view == "family":
        if not args.family:
            print("--family is required for view=family", file=sys.stderr)
            return 2
        result = view_family(filtered, args.family)
    elif args.view == "goals":
        result = view_goals(filtered)
    elif args.view == "effective":
        result = view_effective(filtered)
    elif args.view == "journal":
        result = view_journal(filtered)
    elif args.view == "principles":
        if args.json:
            json.dump(
                view_principles(filtered), sys.stdout, indent=2, ensure_ascii=False
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(render_principles_block(filtered))
        return 0
    elif args.view == "changes-summary":
        activity = [f for f in filtered if f.kind != "principle"]
        if args.json:
            json.dump(
                view_changes_summary(activity), sys.stdout, ensure_ascii=False
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(render_changes_summary_block(activity) + "\n")
        return 0
    else:
        result = view_list(filtered)

    if args.json:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        _format_human(args.view, result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
