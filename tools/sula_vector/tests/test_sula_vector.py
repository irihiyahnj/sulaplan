"""Sula Vector v1.0 test suite (stdlib unittest only).

Covers:
- frontmatter parser (required/optional fields, lists, booleans, malformed)
- fragment loading (skip invalid, sort by time)
- views (digest, list, progress, family, thread, goals, principles, changes-summary)
- render --for-agent (principles prepended, byte-stable, principle-free recent activity)
- migrate.py (idempotence, kind assignment for change-records, releases, events)
- verifier-shell skill (closes goals, idempotent)
- scheduler skill (fires when due, silent when not)
- llm-dispatcher skill (echoes via cat executor, idempotent)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from render import (  # type: ignore  # noqa: E402
    CONVENTION_VERSION,
    LANE_TITLES,
    Fragment,
    _parse_frontmatter,
    derive_identity,
    filter_fragments,
    judgment_gap,
    lane_of,
    load_fragments,
    load_report,
    render_changes_summary_block,
    render_for_agent,
    render_principles_block,
    view_changes_summary,
    view_digest,
    view_doctor,
    view_effective,
    view_family,
    view_goals,
    view_journal,
    view_list,
    view_principles,
    view_progress,
    view_thread,
)


def _make_root() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="sula-test-"))
    frags = root / "fragments"
    frags.mkdir()
    return root, frags


def _write(
    frags_dir: Path,
    *,
    time: str,
    slug: str,
    kind: str,
    body: str = "",
    refs: list[str] | None = None,
    tags: list[str] | None = None,
    extras: dict[str, object] | None = None,
) -> str:
    safe = time.replace(":", "-")
    fid = f"{safe}--{slug}"
    fm = ["---", f"id: {fid}", f"time: {time}", f"kind: {kind}"]
    if refs:
        fm.append(f"refs: [{', '.join(refs)}]")
    if tags:
        fm.append(f"tags: [{', '.join(tags)}]")
    if extras:
        for k, v in extras.items():
            fm.append(f"{k}: {v}")
    fm.append("---")
    (frags_dir / f"{fid}.md").write_text(
        "\n".join(fm) + "\n" + body + "\n", encoding="utf-8"
    )
    return fid


class TestFrontmatterParser(unittest.TestCase):
    def test_required_fields(self):
        text = "---\nid: a\ntime: 2026-05-23T00:00:00Z\nkind: decision\n---\nbody"
        meta, body = _parse_frontmatter(text)
        self.assertEqual(meta["id"], "a")
        self.assertEqual(meta["time"], "2026-05-23T00:00:00Z")
        self.assertEqual(meta["kind"], "decision")
        self.assertEqual(body, "body")

    def test_inline_list(self):
        text = "---\nid: x\ntime: 2026-05-23T00:00:00Z\nkind: x\nrefs: [a, b, c]\n---\n"
        meta, _ = _parse_frontmatter(text)
        self.assertEqual(meta["refs"], ["a", "b", "c"])

    def test_quoted_value(self):
        text = '---\nid: x\ntime: t\nkind: "decision"\n---\nbody'
        meta, _ = _parse_frontmatter(text)
        self.assertEqual(meta["kind"], "decision")

    def test_booleans(self):
        text = "---\nid: x\ntime: t\nkind: x\npinned: true\npassed: false\n---\nbody"
        meta, _ = _parse_frontmatter(text)
        self.assertTrue(meta["pinned"])
        self.assertFalse(meta["passed"])

    def test_no_frontmatter(self):
        meta, body = _parse_frontmatter("just text")
        self.assertEqual(meta, {})
        self.assertEqual(body, "just text")

    def test_unterminated_frontmatter(self):
        text = "---\nid: x\ntime: t\nkind: x\nno closing"
        meta, _ = _parse_frontmatter(text)
        self.assertEqual(meta, {})

    def test_empty_block_list(self):
        text = "---\nid: x\ntime: t\nkind: x\nrefs:\n  - one\n  - two\n---\nbody"
        meta, _ = _parse_frontmatter(text)
        self.assertEqual(meta["refs"], ["one", "two"])


class TestFragmentLoading(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_never_drops_file_without_frontmatter(self):
        (self.frags / "junk.md").write_text("just text", encoding="utf-8")
        frags, problems = load_report(self.frags)
        self.assertEqual(len(frags), 1)
        self.assertIn("no-frontmatter", {p.code for p in problems})

    def test_never_drops_file_missing_kind(self):
        (self.frags / "broken.md").write_text("---\nid: x\n---\nbody", encoding="utf-8")
        frags, problems = load_report(self.frags)
        self.assertEqual(len(frags), 1)
        self.assertEqual(frags[0].kind, "unknown")
        self.assertIn("missing-kind", {p.code for p in problems})

    def test_loads_valid(self):
        _write(self.frags, time="2026-05-23T00:00:00Z", slug="d", kind="decision")
        loaded = load_fragments(self.frags)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].kind, "decision")

    def test_orders_by_time(self):
        _write(self.frags, time="2026-05-23T02:00:00Z", slug="b", kind="fact", body="B")
        _write(self.frags, time="2026-05-23T01:00:00Z", slug="a", kind="fact", body="A")
        loaded = load_fragments(self.frags)
        self.assertEqual([f.body for f in loaded], ["A", "B"])

    def test_recursive_load(self):
        sub = self.frags / "sub"
        sub.mkdir()
        _write(sub, time="2026-05-23T00:00:00Z", slug="d", kind="decision")
        self.assertEqual(len(load_fragments(self.frags)), 1)


class TestViews(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()
        # one decision, one fact, one open goal, one closed intent
        _write(self.frags, time="2026-05-01T00:00:00Z", slug="d1", kind="decision", body="D1")
        _write(self.frags, time="2026-05-02T00:00:00Z", slug="f1", kind="fact", body="F1")
        _write(
            self.frags,
            time="2026-05-03T00:00:00Z",
            slug="g1",
            kind="goal",
            body="G1",
            extras={"done_when": "x", "verifier_ref": "shell:true"},
        )
        intent_id = _write(
            self.frags,
            time="2026-05-04T00:00:00Z",
            slug="i1",
            kind="intent",
            body="I1",
            extras={"done_when": "y"},
        )
        _write(
            self.frags,
            time="2026-05-05T00:00:00Z",
            slug="vf1",
            kind="verification-fact",
            body="vf",
            refs=[intent_id],
            extras={"passed": "true"},
        )

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_digest_separates_decisions_intents_recent(self):
        d = view_digest(load_fragments(self.frags))
        self.assertEqual(len(d["decisions"]), 1)
        # only the goal stays open; intent was satisfied
        self.assertEqual(len(d["open_intents"]), 1)
        self.assertIn("g1", d["open_intents"][0]["id"])

    def test_progress_joins_verification(self):
        rows = view_progress(load_fragments(self.frags))
        # only intents/goals with done_when count
        self.assertEqual(len(rows), 2)
        met = [r for r in rows if r["met"]]
        self.assertEqual(len(met), 1)
        self.assertIn("i1", met[0]["intent"]["id"])

    def test_goals_view(self):
        rows = view_goals(load_fragments(self.frags))
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["met"])

    def test_changes_summary_counts(self):
        s = view_changes_summary(load_fragments(self.frags))
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["by_kind"]["decision"], 1)
        self.assertEqual(s["by_kind"]["verification-fact"], 1)
        self.assertEqual(len(s["fragments"]), 5)

    def test_changes_summary_block_silent_on_empty(self):
        self.assertEqual(render_changes_summary_block([]), "[sula] no changes")

    def test_changes_summary_block_marks_pass(self):
        block = render_changes_summary_block(load_fragments(self.frags))
        self.assertIn("[sula] +5 this turn:", block)
        self.assertIn("✓ verification-fact", block)


class TestThreadAndFamily(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()
        _write(self.frags, time="2026-05-01T00:00:00Z", slug="t1", kind="turn",
               extras={"thread_id": "alpha"})
        _write(self.frags, time="2026-05-02T00:00:00Z", slug="t2", kind="turn",
               extras={"thread_id": "alpha"})
        _write(self.frags, time="2026-05-03T00:00:00Z", slug="a1", kind="artifact",
               extras={"family_key": "X", "artifact_role": "workspace-source", "pointer": "src/x.md"})
        _write(self.frags, time="2026-05-04T00:00:00Z", slug="a2", kind="artifact",
               extras={"family_key": "X", "artifact_role": "exported-derivative", "pointer": "exports/x.docx"})

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_thread_view(self):
        rows = view_thread(load_fragments(self.frags), "alpha")
        self.assertEqual(len(rows), 2)

    def test_family_latest_by_role(self):
        v = view_family(load_fragments(self.frags), "X")
        self.assertEqual(set(v["latest_by_role"].keys()),
                         {"workspace-source", "exported-derivative"})


class TestForAgentRender(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()
        _write(
            self.frags,
            time="2026-05-23T04:50:00Z",
            slug="principle-tier-A",
            kind="principle",
            body="Highest rule body.",
            extras={"tier": "highest"},
        )
        _write(self.frags, time="2026-05-22T00:00:00Z", slug="d1", kind="decision", body="D1")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_principles_prepended(self):
        out = render_for_agent(load_fragments(self.frags), project_name="T")
        self.assertIn("Principles in force", out)
        self.assertLess(
            out.index("Highest rule body."), out.index(LANE_TITLES["evidence"])
        )

    def test_principles_excluded_from_activity(self):
        out = render_for_agent(load_fragments(self.frags))
        position = out.split(f"## {LANE_TITLES['evidence']}", 1)[1]
        self.assertNotIn("principle", position)

    def test_three_lanes_present(self):
        out = render_for_agent(load_fragments(self.frags))
        for lane in ("judgment", "direction", "evidence"):
            self.assertIn(f"## {LANE_TITLES[lane]}", out)

    def test_byte_stable(self):
        a = render_for_agent(load_fragments(self.frags))
        b = render_for_agent(load_fragments(self.frags))
        self.assertEqual(a, b)


class TestMigrateIdempotence(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sula-test-mig-"))
        # Build a synthetic legacy Sula project layout
        (self.root / "docs" / "change-records").mkdir(parents=True)
        (self.root / "docs" / "releases").mkdir(parents=True)
        sula = self.root / ".sula"
        (sula / "events").mkdir(parents=True)
        (sula / "artifacts").mkdir(parents=True)
        (self.root / "docs" / "change-records" / "2026-05-01-foo.md").write_text(
            "# Foo\n\nBody.\n", encoding="utf-8"
        )
        (self.root / "docs" / "releases" / "2026-05-02-release-x.md").write_text(
            "# Release X\n", encoding="utf-8"
        )
        (self.root / "STATUS.md").write_text("# STATUS\nbody\n", encoding="utf-8")
        (sula / "project.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
        (sula / "events" / "log.jsonl").write_text(
            '{"timestamp":"2026-05-01T00:00:00Z","event_type":"record.change","summary":"X"}\n'
            '{"timestamp":"2026-05-01T00:00:00Z","event_type":"record.change","summary":"X"}\n'  # dup
            '{"timestamp":"2026-05-01T00:00:01Z","event_type":"sync.applied","summary":"noise"}\n',
            encoding="utf-8",
        )
        (sula / "artifacts" / "catalog.json").write_text(
            json.dumps({"artifacts": [{"id": "a1", "title": "A1", "kind": "report"}]}),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.root)

    def _run_migrate(self):
        result = subprocess.run(
            [
                "python3",
                str(TOOLS / "migrate.py"),
                "--project-root",
                str(self.root),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_first_run_produces_expected_kinds(self):
        self._run_migrate()
        frags = load_fragments(self.root / "fragments")
        kinds = {f.kind for f in frags}
        self.assertIn("decision", kinds)  # change-record + manifest + migration-decision
        self.assertIn("release", kinds)
        self.assertIn("snapshot", kinds)  # STATUS.md
        self.assertIn("artifact", kinds)
        self.assertIn("event", kinds)

    def test_second_run_is_noop(self):
        self._run_migrate()
        before = sorted(p.name for p in (self.root / "fragments").glob("*.md"))
        self._run_migrate()
        after = sorted(p.name for p in (self.root / "fragments").glob("*.md"))
        self.assertEqual(before, after)

    def test_event_dedup(self):
        self._run_migrate()
        events = [
            f
            for f in load_fragments(self.root / "fragments")
            if f.kind == "event"
        ]
        # Two duplicate record.change events in source must collapse to one
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get("event_type"), "record.change")

    def test_legacy_dirs_untouched(self):
        self._run_migrate()
        self.assertTrue((self.root / ".sula").is_dir())
        self.assertTrue((self.root / "STATUS.md").exists())
        self.assertTrue(
            (self.root / "docs" / "change-records" / "2026-05-01-foo.md").exists()
        )


class TestVerifierShellSkill(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _run(self):
        result = subprocess.run(
            [
                "python3",
                str(TOOLS / "skills" / "verifier-shell.py"),
                "--project-root",
                str(self.root),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_closes_goal_with_passing_command(self):
        gid = _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="goal-true",
            kind="goal",
            body="must run true",
            extras={"done_when": "true exits 0", "verifier_ref": "shell:true"},
        )
        self._run()
        verified = [
            f
            for f in load_fragments(self.frags)
            if f.kind == "verification-fact" and gid in f.refs
        ]
        self.assertEqual(len(verified), 1)
        self.assertIn(verified[0].get("passed"), {True, "true"})

    def test_idempotent_on_satisfied_goal(self):
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="goal-true2",
            kind="goal",
            extras={"done_when": "true", "verifier_ref": "shell:true"},
        )
        self._run()
        before = len(list(self.frags.glob("*.md")))
        self._run()
        after = len(list(self.frags.glob("*.md")))
        self.assertEqual(before, after)


class TestSchedulerSkill(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _run(self):
        result = subprocess.run(
            [
                "python3",
                str(TOOLS / "skills" / "scheduler.py"),
                "--project-root",
                str(self.root),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_fires_overdue_intent(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        _write(
            self.frags,
            time=past,
            slug="intent-overdue",
            kind="intent",
            body="heartbeat",
            extras={"cadence": "every-1m"},
        )
        self._run()
        ticks = [f for f in load_fragments(self.frags) if f.kind == "cadence-tick"]
        self.assertEqual(len(ticks), 1)

    def test_skips_recent_intent(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write(
            self.frags,
            time=now,
            slug="intent-fresh",
            kind="intent",
            body="heartbeat",
            extras={"cadence": "every-10m"},
        )
        self._run()
        ticks = [f for f in load_fragments(self.frags) if f.kind == "cadence-tick"]
        self.assertEqual(len(ticks), 0)


class TestLLMDispatcherSkill(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _run(self):
        result = subprocess.run(
            [
                "python3",
                str(TOOLS / "skills" / "llm-dispatcher.py"),
                "--project-root",
                str(self.root),
                "--timeout",
                "30",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_dispatches_with_cat_executor(self):
        iid = _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="intent-cat",
            kind="intent",
            body="hello world via cat",
            extras={"executor_command": "cat"},
        )
        self._run()
        turns = [
            f
            for f in load_fragments(self.frags)
            if f.kind == "turn" and iid in f.refs
        ]
        self.assertEqual(len(turns), 1)
        self.assertIn("hello world via cat", turns[0].body)

    def test_idempotent(self):
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="intent-cat2",
            kind="intent",
            body="x",
            extras={"executor_command": "cat"},
        )
        self._run()
        before = len(list(self.frags.glob("*.md")))
        self._run()
        after = len(list(self.frags.glob("*.md")))
        self.assertEqual(before, after)


class TestConventionVersion(unittest.TestCase):
    def test_version_is_one_one(self):
        self.assertEqual(CONVENTION_VERSION, "1.1")


class TestDerivedIdentity(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_identity_comes_from_filename(self):
        stem = "2026-07-01T09-08-07Z--decision-x"
        (self.frags / f"{stem}.md").write_text(
            "---\nkind: decision\n---\nonly kind was authored\n", encoding="utf-8"
        )
        frags, problems = load_report(self.frags)
        self.assertEqual(problems, [])
        self.assertEqual(frags[0].id, stem)
        self.assertEqual(frags[0].time, "2026-07-01T09:08:07Z")

    def test_derive_identity_helper(self):
        fid, time = derive_identity(Path("2026-07-01T09-08-07Z--goal-y.md"))
        self.assertEqual(fid, "2026-07-01T09-08-07Z--goal-y")
        self.assertEqual(time, "2026-07-01T09:08:07Z")

    def test_frontmatter_disagreement_is_reported_filename_wins(self):
        stem = "2026-07-01T09-08-07Z--decision-x"
        (self.frags / f"{stem}.md").write_text(
            "---\nid: wrong-id\ntime: 2020-01-01T00:00:00Z\nkind: decision\n---\nb\n",
            encoding="utf-8",
        )
        frags, problems = load_report(self.frags)
        codes = [p.code for p in problems]
        self.assertEqual(codes.count("header-disagreement"), 2)
        self.assertEqual(frags[0].id, stem)
        self.assertEqual(frags[0].time, "2026-07-01T09:08:07Z")


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _doctor(self):
        frags, problems = load_report(self.frags)
        return view_doctor(frags, problems)

    def test_clean_vector_is_ok(self):
        _write(self.frags, time="2026-05-23T00:00:00Z", slug="d", kind="decision", body="x")
        report = self._doctor()
        self.assertTrue(report["ok"])
        self.assertEqual(report["problems"], [])

    def test_dangling_ref_detected(self):
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="d",
            kind="decision",
            body="x",
            refs=["2026-01-01T00-00-00Z--does-not-exist"],
        )
        self.assertIn("dangling-ref", self._doctor()["by_code"])

    def test_dangling_ref_acknowledged_by_correction(self):
        missing = "2026-01-01T00-00-00Z--does-not-exist"
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="d",
            kind="decision",
            body="x",
            refs=[missing],
        )
        _write(
            self.frags,
            time="2026-05-24T00:00:00Z",
            slug="correction-ack",
            kind="correction",
            body="that id never existed",
            extras={"broken_ref": missing},
        )
        self.assertTrue(self._doctor()["ok"])

    def test_goal_without_verifier_detected(self):
        _write(self.frags, time="2026-05-23T00:00:00Z", slug="g", kind="goal", body="x")
        self.assertIn("goal-without-verifier", self._doctor()["by_code"])

    def test_symbolic_refs_are_not_dangling(self):
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="d",
            kind="decision",
            body="x",
            refs=["family:acme-intake"],
        )
        self.assertTrue(self._doctor()["ok"])

    def test_cli_exit_code(self):
        _write(
            self.frags,
            time="2026-05-23T00:00:00Z",
            slug="d",
            kind="decision",
            body="x",
            refs=["nope"],
        )
        result = subprocess.run(
            [sys.executable, str(TOOLS / "render.py"), str(self.root), "--view", "doctor"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("dangling-ref", result.stdout)


class TestSupersessionAndClosure(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()
        self.old = _write(
            self.frags, time="2026-05-01T00:00:00Z", slug="d-old", kind="decision", body="old way"
        )
        self.new = _write(
            self.frags,
            time="2026-05-02T00:00:00Z",
            slug="d-new",
            kind="decision",
            body="new way",
            extras={"supersedes": f"[{self.old}]"},
        )

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_effective_splits_in_force_and_retired(self):
        result = view_effective(load_fragments(self.frags))
        self.assertEqual([f["id"] for f in result["in_force"]], [self.new])
        self.assertEqual([f["id"] for f in result["retired"]], [self.old])
        self.assertEqual(result["retired"][0]["superseded_by"][0]["id"], self.new)

    def test_superseded_judgment_hidden_from_boot(self):
        out = render_for_agent(load_fragments(self.frags))
        self.assertIn(self.new, out)
        self.assertNotIn(self.old, out)
        self.assertIn("superseded judgment", out)

    def test_closes_removes_open_direction(self):
        intent = _write(
            self.frags, time="2026-05-03T00:00:00Z", slug="i", kind="intent", body="do a thing"
        )
        digest = view_digest(load_fragments(self.frags))
        self.assertIn(intent, [d["id"] for d in digest["open_intents"]])
        _write(
            self.frags,
            time="2026-05-04T00:00:00Z",
            slug="f",
            kind="fact",
            body="thing done",
            extras={"closes": f"[{intent}]"},
        )
        digest = view_digest(load_fragments(self.frags))
        self.assertEqual(digest["open_intents"], [])

    def test_superseded_principle_leaves_force(self):
        p_old = _write(
            self.frags,
            time="2026-05-05T00:00:00Z",
            slug="principle-old",
            kind="principle",
            body="old principle",
            extras={"tier": "aesthetic"},
        )
        _write(
            self.frags,
            time="2026-05-06T00:00:00Z",
            slug="principle-new",
            kind="principle",
            body="new principle",
            extras={"tier": "aesthetic", "supersedes": f"[{p_old}]"},
        )
        bodies = [
            p["body"] for p in view_principles(load_fragments(self.frags))["aesthetic"]
        ]
        self.assertEqual(bodies, ["new principle"])


class TestLanesAndJournal(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_lane_defaults(self):
        cases = {
            "decision": "judgment",
            "correction": "judgment",
            "goal": "direction",
            "intent": "direction",
            "witness": "evidence",
            "artifact": "evidence",
            "some-new-kind": "evidence",
        }
        for kind, lane in cases.items():
            self.assertEqual(lane_of(Fragment(id="x", time="t", kind=kind)), lane)

    def test_explicit_lane_overrides(self):
        f = Fragment(id="x", time="t", kind="artifact", extra={"lane": "judgment"})
        self.assertEqual(lane_of(f), "judgment")

    def test_lane_filter(self):
        _write(self.frags, time="2026-05-01T00:00:00Z", slug="d", kind="decision", body="d")
        _write(self.frags, time="2026-05-02T00:00:00Z", slug="w", kind="witness", body="w")
        frags = load_fragments(self.frags)
        self.assertEqual(len(filter_fragments(frags, lane="judgment")), 1)
        self.assertEqual(len(filter_fragments(frags, lane="evidence")), 1)

    def test_journal_groups_by_day(self):
        _write(self.frags, time="2026-05-01T09:00:00Z", slug="d", kind="decision", body="chose X")
        _write(
            self.frags,
            time="2026-05-01T10:00:00Z",
            slug="a",
            kind="artifact",
            body="proposal",
            extras={"pointer": "docs/p.pdf"},
        )
        _write(self.frags, time="2026-05-02T09:00:00Z", slug="w", kind="witness", body="+1 file")
        journal = view_journal(load_fragments(self.frags))
        self.assertEqual([d["day"] for d in journal], ["2026-05-01", "2026-05-02"])
        self.assertEqual(len(journal[0]["judgment"]), 1)
        self.assertEqual(journal[0]["evidence"][0]["pointer"], "docs/p.pdf")


class TestNoteCli(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _note(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOLS / "note.py"), str(self.root), *args],
            capture_output=True,
            text=True,
        )

    def test_appends_clean_fragment(self):
        result = self._note("--kind", "decision", "--title", "pick A", "because faster")
        self.assertEqual(result.returncode, 0, result.stderr)
        frags, problems = load_report(self.frags)
        self.assertEqual(problems, [])
        self.assertEqual(len(frags), 1)
        self.assertEqual(frags[0].kind, "decision")
        self.assertEqual(frags[0].get("summary"), "pick A")
        self.assertEqual(frags[0].id, Path(frags[0].path).stem)

    def test_echoes_derived_lane(self):
        result = self._note("--kind", "decision", "--title", "pick A", "why")
        self.assertIn("→ judgment", result.stdout)
        result = self._note("--kind", "event", "--title", "a thing happened", "what")
        self.assertIn("→ evidence", result.stdout)

    def test_rejects_unknown_ref(self):
        result = self._note("--kind", "decision", "--refs", "nope", "body")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.frags.glob("*.md")), [])

    def test_rejects_goal_without_verifier(self):
        result = self._note("--kind", "goal", "--title", "ship it", "body")
        self.assertEqual(result.returncode, 2)

    def test_non_ascii_body_yields_safe_filename(self):
        result = self._note("--kind", "decision", "对 Acme 采用月度交付节奏")
        self.assertEqual(result.returncode, 0, result.stderr)
        name = next(self.frags.glob("*.md")).name
        self.assertTrue(name.isascii(), name)

    def test_same_second_appends_do_not_collide(self):
        for _ in range(3):
            self.assertEqual(self._note("--kind", "fact", "--title", "same", "x").returncode, 0)
        frags, problems = load_report(self.frags)
        self.assertEqual(len(frags), 3)
        self.assertNotIn("duplicate-id", view_doctor(frags, problems)["by_code"])


class TestWitnessSkill(unittest.TestCase):
    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _witness(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(TOOLS / "skills" / "witness.py"),
                "--project-root",
                str(self.root),
                *args,
            ],
            capture_output=True,
            text=True,
        )

    def test_newline_in_filename_does_not_churn(self):
        """A newline in a filename must not break the delta round-trip.

        Found on an iCloud folder of documents synced from another tool: the
        path split the delta line, folded back truncated, and the file was
        reported added and removed on every run forever.
        """
        (self.root / "note\nwith newline.md").write_text("x", encoding="utf-8")
        self.assertEqual(self._witness().returncode, 0)
        second = self._witness()
        self.assertIn("no change", second.stdout)

    def test_captures_added_changed_removed(self):
        (self.root / "notes.md").write_text("one", encoding="utf-8")
        self.assertEqual(self._witness().returncode, 0)
        witnesses = [f for f in load_fragments(self.frags) if f.kind == "witness"]
        self.assertEqual(len(witnesses), 1)
        self.assertEqual(witnesses[0].get("files_added"), "1")

        (self.root / "notes.md").write_text("two", encoding="utf-8")
        self._witness()
        (self.root / "notes.md").unlink()
        self._witness()
        witnesses = [f for f in load_fragments(self.frags) if f.kind == "witness"]
        self.assertEqual(len(witnesses), 3)
        self.assertEqual(witnesses[1].get("files_changed"), "1")
        self.assertEqual(witnesses[2].get("files_removed"), "1")

    def test_idempotent_when_nothing_changed(self):
        (self.root / "notes.md").write_text("one", encoding="utf-8")
        self._witness()
        before = len(list(self.frags.glob("*.md")))
        result = self._witness()
        self.assertIn("no change", result.stdout)
        self.assertEqual(len(list(self.frags.glob("*.md"))), before)

    def test_documents_become_artifact_fragments(self):
        (self.root / "proposal.pdf").write_text("pdf", encoding="utf-8")
        (self.root / "script.py").write_text("code", encoding="utf-8")
        self._witness()
        frags = load_fragments(self.frags)
        artifacts = [f for f in frags if f.kind == "artifact"]
        self.assertEqual([f.get("pointer") for f in artifacts], ["proposal.pdf"])

    def test_state_is_folded_not_stored(self):
        (self.root / "a.md").write_text("a", encoding="utf-8")
        self._witness()
        self.assertFalse((self.root / ".sula").exists())
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()), ["a.md", "fragments"]
        )

    def test_output_is_clean_for_doctor(self):
        (self.root / "proposal.pdf").write_text("pdf", encoding="utf-8")
        self._witness("--label", "定稿")
        frags, problems = load_report(self.frags)
        self.assertTrue(view_doctor(frags, problems)["ok"])

    def test_rejects_unknown_refs(self):
        (self.root / "a.md").write_text("a", encoding="utf-8")
        result = self._witness("--refs", "nope")
        self.assertEqual(result.returncode, 2)

    def test_fragment_only_commits_do_not_loop(self):
        def git(*cmd):
            subprocess.run(["git", *cmd], cwd=str(self.root), check=True,
                           capture_output=True, text=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (self.root / "report.md").write_text("v1", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "add report")
        self.assertEqual(self._witness().returncode, 0)
        # commit the witness fragment itself, then witness again: no churn
        git("add", "-A")
        git("commit", "-qm", "capture")
        before = len(list(self.frags.glob("*.md")))
        result = self._witness()
        self.assertIn("no change", result.stdout)
        self.assertEqual(len(list(self.frags.glob("*.md"))), before)


class TestBootCompleteness(unittest.TestCase):
    """A lane's cutoff must be its own semantics, never a shared recency cap."""

    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _many(self, kind: str, count: int = 25) -> list[str]:
        return [
            _write(
                self.frags,
                time=f"2026-05-{day:02d}T00:00:00Z",
                slug=f"{kind}-{day}",
                kind=kind,
                body="body",
            )
            for day in range(1, count + 1)
        ]

    def test_every_in_force_judgment_reaches_boot(self):
        ids = self._many("decision")
        out = render_for_agent(load_fragments(self.frags))
        self.assertEqual([i for i in ids if i not in out], [])

    def test_supersession_is_the_only_way_out_of_boot(self):
        ids = self._many("decision")
        retired = ids[0]
        newest = _write(
            self.frags,
            time="2026-06-01T00:00:00Z",
            slug="correction-x",
            kind="correction",
            body="wrong",
            extras={"supersedes": f"[{retired}]"},
        )
        out = render_for_agent(load_fragments(self.frags))
        self.assertNotIn(retired, out)
        self.assertIn(newest, out)
        self.assertEqual([i for i in ids[1:] if i not in out], [])

    def test_every_open_direction_reaches_boot(self):
        ids = self._many("goal")
        digest = view_digest(load_fragments(self.frags))
        self.assertEqual([d["id"] for d in digest["open_intents"]], ids)

    def test_evidence_stays_capped_by_recency(self):
        ids = self._many("event")
        digest = view_digest(load_fragments(self.frags))
        self.assertEqual([d["id"] for d in digest["recent"]], ids[-10:])

    def test_untiered_project_principle_reaches_every_view(self):
        """`tier` groups principles, it never filters them.

        A project's own principle carries no Tier A–E label. Dropping it made
        the most load-bearing judgment in a real project invisible in both
        --for-agent and --view principles while the file sat in fragments/.
        """
        _write(
            self.frags,
            time="2026-05-09T00:00:00Z",
            slug="principle-house-rule",
            kind="principle",
            body="Never haggle over her cost price.",
        )
        frags = load_fragments(self.frags)
        grouped = view_principles(frags)
        self.assertEqual(
            [p["body"] for p in grouped["project"]],
            ["Never haggle over her cost price."],
        )
        self.assertIn("Never haggle", render_principles_block(frags))
        self.assertIn("Never haggle", render_for_agent(frags))

    def test_boot_membership_matches_effective(self):
        """No two views may disagree about the same lane's membership.

        The n=10 defect was invisible to every test because the tests shared its
        belief. Cross-view agreement is checkable without knowing the intent.
        """
        ids = self._many("decision")
        retired = ids[3]
        _write(
            self.frags,
            time="2026-06-02T00:00:00Z",
            slug="correction-y",
            kind="correction",
            body="wrong",
            extras={"supersedes": f"[{retired}]"},
        )
        frags = load_fragments(self.frags)
        out = render_for_agent(frags)
        effective = view_effective(frags)
        for f in effective["in_force"]:
            if f["kind"] != "principle":
                self.assertIn(f["id"], out)
        for f in effective["retired"]:
            self.assertNotIn(f["id"], out)


class TestJudgmentGap(unittest.TestCase):
    """Witnessed change without a judgment must be visible, never fatal."""

    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _witness(self, time: str, slug: str, **extras: object) -> str:
        fields: dict[str, object] = {
            "files_added": 0,
            "files_changed": 2,
            "files_removed": 0,
        }
        fields.update(extras)
        return _write(
            self.frags,
            time=time,
            slug=slug,
            kind="witness",
            body="+0 ~2 -0 file(s).",
            extras=fields,
        )

    def test_change_without_judgment_is_reported(self):
        wid = self._witness("2026-05-02T00:00:00Z", "witness-a")
        frags = load_fragments(self.frags)
        self.assertEqual([f.id for f in judgment_gap(frags)], [wid])
        self.assertIn("Unexplained change", render_for_agent(frags))
        self.assertIn("no judgment recorded", render_changes_summary_block(frags))

    def test_later_judgment_clears_the_gap(self):
        self._witness("2026-05-02T00:00:00Z", "witness-a")
        _write(
            self.frags,
            time="2026-05-03T00:00:00Z",
            slug="d",
            kind="decision",
            body="why it changed",
        )
        frags = load_fragments(self.frags)
        self.assertEqual(judgment_gap(frags), [])
        self.assertNotIn("Unexplained change", render_for_agent(frags))

    def test_later_direction_also_clears_the_gap(self):
        self._witness("2026-05-02T00:00:00Z", "witness-a")
        _write(
            self.frags,
            time="2026-05-03T00:00:00Z",
            slug="g",
            kind="goal",
            body="where this is going",
            extras={"verifier_ref": "shell: true"},
        )
        self.assertEqual(judgment_gap(load_fragments(self.frags)), [])

    def test_evidence_alone_never_clears_the_gap(self):
        wid = self._witness("2026-05-02T00:00:00Z", "witness-a")
        _write(
            self.frags,
            time="2026-05-03T00:00:00Z",
            slug="vf",
            kind="verification-fact",
            body="passed",
            extras={"passed": "true"},
        )
        self.assertEqual(
            [f.id for f in judgment_gap(load_fragments(self.frags))], [wid]
        )

    def test_judgment_before_hook_fired_witness_is_not_a_gap(self):
        """The hook fires at turn end, so the witness lands after the judgment.

        Keying on timestamps alone flags every well-behaved turn. The window
        between two captures is the unit, not the instant.
        """
        _write(
            self.frags,
            time="2026-05-02T00:00:00Z",
            slug="d",
            kind="decision",
            body="why I changed those files",
        )
        self._witness("2026-05-02T00:00:05Z", "witness-a")
        self.assertEqual(judgment_gap(load_fragments(self.frags)), [])

    def test_second_turn_without_judgment_is_a_gap(self):
        _write(
            self.frags,
            time="2026-05-02T00:00:00Z",
            slug="d",
            kind="decision",
            body="why turn one changed files",
        )
        self._witness("2026-05-02T00:00:05Z", "witness-a")
        wid = self._witness("2026-05-03T00:00:00Z", "witness-b")
        self.assertEqual(
            [f.id for f in judgment_gap(load_fragments(self.frags))], [wid]
        )

    def test_baseline_and_silent_witness_are_not_gaps(self):
        self._witness(
            "2026-05-02T00:00:00Z", "witness-baseline", files_added=300, baseline="true"
        )
        self._witness("2026-05-03T00:00:00Z", "witness-quiet", files_changed=0)
        self.assertEqual(judgment_gap(load_fragments(self.frags)), [])

    def test_gap_is_not_a_doctor_problem(self):
        self._witness("2026-05-02T00:00:00Z", "witness-a")
        frags, problems = load_report(self.frags)
        self.assertTrue(view_doctor(frags, problems)["ok"])


class TestCaptureInstaller(unittest.TestCase):
    """The installer must only claim installs the host actually reads."""

    KIRO_CLI_TRIGGERS = {
        "agentSpawn",
        "userPromptSubmit",
        "preToolUse",
        "postToolUse",
        "stop",
    }

    def setUp(self):
        self.root, self.frags = _make_root()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(TOOLS / "hooks" / "install.py"),
                "--project-root",
                str(self.root),
                "--skip-schedule",
                *args,
            ],
            capture_output=True,
            text=True,
        )

    def test_cli_agent_uses_only_documented_triggers(self):
        """Kiro CLI has no agentStop trigger and never reads .kiro/hooks/.

        The installer shipped an agentStop hook for two releases and reported it
        as installed, so capture was silently dead on every non-git substrate.
        """
        self.assertEqual(self._install().returncode, 0)
        config = json.loads(
            (self.root / ".kiro" / "agents" / "sula.json").read_text(encoding="utf-8")
        )
        triggers = set(config["hooks"])
        self.assertTrue(triggers)
        self.assertEqual(triggers - self.KIRO_CLI_TRIGGERS, set())
        self.assertIn("agentSpawn", triggers)
        self.assertIn("stop", triggers)

    def test_ide_hook_is_labelled_as_ide_only(self):
        out = self._install().stdout
        self.assertIn("Kiro IDE only", out)
        self.assertRegex(out, r"kiro-cli\s+.*sula\.json")

    def test_cli_agent_reported_inactive_until_selected(self):
        self.assertIn("NOT active", self._install().stdout)
        (self.root / ".kiro" / "settings").mkdir(parents=True, exist_ok=True)
        (self.root / ".kiro" / "settings" / "cli.json").write_text(
            json.dumps({"chat.defaultAgent": "sula"}), encoding="utf-8"
        )
        self.assertIn("active", self._install().stdout)

    def test_install_is_idempotent(self):
        self._install()
        second = self._install()
        self.assertIn("already installed", second.stdout)


class TestHostPointers(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sula-test-host-"))

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_projects_all_hosts_and_is_idempotent(self):
        sys.path.insert(0, str(TOOLS))
        from migrate import HOST_POINTER_TARGETS, install_host_pointers  # type: ignore

        written = install_host_pointers(self.root)
        self.assertEqual(written, len(HOST_POINTER_TARGETS))
        for rel in HOST_POINTER_TARGETS:
            text = (self.root / rel).read_text(encoding="utf-8")
            self.assertIn("AGENTS.md", text)
            self.assertIn("--for-agent", text)
        self.assertEqual(install_host_pointers(self.root), 0)

    def test_agents_protocol_is_projected_from_template(self):
        sys.path.insert(0, str(TOOLS))
        from migrate import install_agents_template  # type: ignore

        (self.root / "AGENTS.md").write_text("# legacy rules\n", encoding="utf-8")
        install_agents_template(self.root, TOOLS / "AGENTS.md")
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- sula-vector -->", text)
        self.assertIn("Three lanes", text)
        self.assertNotIn("path/to/", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
