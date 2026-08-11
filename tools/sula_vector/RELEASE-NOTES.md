# Sula Vector — Release Notes

## v1.1.3 — Capture is wired to hosts that actually read it

**Release date:** 2026-07-26
**Convention version:** 1.1 (unchanged; installer and docs)

`hooks/install.py` wrote `.kiro/hooks/sula-witness.kiro.hook` with trigger
`agentStop` and reported `kiro installed`. Kiro CLI reads hooks only from a
`hooks` field inside an agent configuration, and its trigger set is
`agentSpawn`, `userPromptSubmit`, `preToolUse`, `postToolUse`, `stop` — there is
no `agentStop`, and `.kiro/hooks/` is the IDE's location. So on every substrate
without git, mechanical capture had been dead since v1.1 while the installer
claimed success. A tool whose purpose is an honest record must not misreport its
own wiring.

- Kiro CLI now gets `.kiro/agents/sula.json`: `agentSpawn` runs the boot and its stdout is added to the session context, `stop` witnesses the turn. Written but deliberately **not** activated — a custom agent replaces the built-in default agent's prompt, which is not a change to make on a user's behalf. Activate with `kiro-cli settings chat.defaultAgent sula`.
- The IDE hook is still written, now labelled as IDE-only.
- A folder or Drive substrate on macOS gets a **launchd** timer every 900s instead of a printed cron line. cron needs Full Disk Access to read `~/Library/Mobile Documents`; launchd runs in the user session and does not. Verified end to end on an iCloud project: a file change produced a witness fragment.
- launchd labels carry a path digest. The readable part of a CJK-only folder name reduces to nothing, and two such projects would otherwise share one label and evict each other.

`install.py` had no test coverage at all, which is why a false success report
survived two releases. It now has four tests, one of which pins the documented
trigger set.

## v1.1.2 — The missing why is inherited, not forgotten

**Release date:** 2026-07-25
**Convention version:** 1.1 (unchanged; new notice in two existing views)

Evidence capture was mechanical from v1.1; judgment capture was not, and could
not be. But the *omission* is computable: `judgment_gap()` returns every
witness fragment recording real change that no judgment and no direction
follows. Evidence is the one lane a machine can write, so evidence alone leaves
the why nowhere.

- The end-of-turn mark gains `! N file change(s) witnessed, no judgment recorded`, so the human sees it in-band at the moment it happens.
- `--for-agent` gains `## Unexplained change`, so a gap left by one session is inherited by the next agent instead of evaporating with the transcript.
- `--view doctor` is deliberately unchanged. A missing judgment is not malformation, and forcing an append would buy E8 with C7. In an append-only store the strongest available enforcement is permanent visibility — the same shape as the trust model: it cannot prevent a false claim, it makes one permanently traceable.

Baseline witnesses and silent witnesses are not gaps.

A cross-view invariant is now pinned by test: no two views may disagree about
one lane's membership. The `n=10` defect fixed in v1.1.1 was invisible to 65
passing tests because those tests shared its belief; view-to-view disagreement
is checkable without knowing the intent, which retires that whole class.

## v1.1.1 — Boot carries all live state

**Release date:** 2026-07-25
**Convention version:** 1.1 (unchanged; renderer defect fix)
**Never tagged standalone.** The gap notice introduced alongside it had a
systematic false positive; both ship together as v1.1.2.

`view_digest` capped all three lanes at the same `n=10`, so `--for-agent`
showed only the ten most recent judgments. On Sula's own vector that meant 92
judgments were in force and 10 reached the boot context — and the line
`(N superseded judgment(s) hidden)` attributed the loss to supersession, which
accounted for 2 of them. Cross-model handover reads the boot; a boot missing
most of the live state makes "switch cost = 0" false for older decisions.

The fix is dimensional, not a knob: a lane's cutoff must be its own semantics.
A judgment ends when superseded, a direction when closed, evidence only
recedes into the past. `n` now means what it always meant — how much recent
evidence to show — and the two other caps are gone. Nothing became
configurable, so no implicit state was traded for a setting (B2).

`note.py` now echoes the derived lane when it appends (`+ decision → judgment`),
so a `kind` that lands in the wrong lane is visible at write time rather than
silently absent from the boot's in-force list.

## v1.1 — Capture as invariant, errors made unrepresentable

**Release date:** 2026-07-25
**Convention version:** 1.1 (backwards-compatible; every v1.0 fragment parses and keeps its meaning)

v1.1 answers a single audit finding: the two things a "record every
interaction" system actually depends on — **capture fidelity** (what reaches
`fragments/`) and **reader resolution** (what `render` resolves for the
reader) — were both enforced at the prompt layer, where failure is silent.
v1.1 moves them to the data and runtime layers.

### Derived identity

- `id` and `time` now come from the **filename**, always. Frontmatter copies are treated as redundant and any disagreement surfaces as a `header-disagreement` problem. A fragment can no longer carry a wrong id or timestamp.
- No fragment is ever silently dropped. A file missing `kind` or with an unparsable name still loads and shows up in `--view doctor`. Silent loss is the one failure an append-only store cannot recover from.
- `note.py` is the write path for judgments: it derives identity from the clock, rejects unknown `refs`/`closes`/`supersedes` targets, and refuses a goal without a verifier. A dangling reference cannot be created through it.

### Three lanes

- Every fragment projects at render time into `judgment` (why), `evidence` (what), or `direction` (where to). `kind` stays a free-form string (B3/E4 intact); the lane is a projection, not an enum. `--for-agent` and `--view journal` are organised by lane; filter with `--lane`.

### Supersession and closure

- `supersedes: [id]` — a judgment replaces earlier ones; superseded judgments (and principles) leave the boot context and the supersession trail appears in `--view effective`.
- `closes: [id]` — any fragment closes an open direction, so intents no longer accumulate forever.

### Mechanical evidence

- `skills/witness.py` captures what changed on **any substrate** — git repo, Drive/Dropbox folder, or plain folder of documents — recording path + content hash per file, plus commit-level detail on git. Prior state is folded out of previous witness fragments; no state directory (B2/B4/E1/E2). Silent when nothing changed (C7). New documents become `kind: artifact` fragments.
- `hooks/install.py` wires the capture trigger the substrate already offers: git `post-commit`, a Kiro CLI agent config, a Kiro IDE hook, or a scheduled timer.

### Reader resolution

- New views: `journal` (day-by-day decided/produced — the human/company view), `effective` (judgments in force + retirement trail), `doctor` (structural integrity, exit 1 on problems; usable as a CI gate and as a goal verifier).

### Boot back to two steps

- Boot is `note session_start` + `render --for-agent`. Tooling auto-update is no longer part of boot (B6); it is an explicit operator action.

### Host convergence

- All five host entrypoints (`CLAUDE.md`, `CODEX.md`, `GEMINI.md`, Cursor, Copilot) are thin pointers to `AGENTS.md`, projected idempotently by `migrate.py`. Legacy Sula 0.18.x files carry a "do not act on this" banner.

Test suite: 65 tests, standard library only. `--view doctor` exits 0 on
Sula's own vector (373 fragments).

---

# Sula Vector v1.0 — Release Notes

**Release date:** 2026-05-23
**Convention version:** 1.0 (ship-frozen)
**Status:** General Availability (GA)

This is the first stable release of Sula Vector. The convention is frozen
for v1.x. Future minor versions add views, kinds, or skills without breaking
existing fragment files.

---

## What v1.0 ships

### Convention (ship-frozen)

- **Tier A** highest rule: `project_view = render(fragments, conventions)`. No mutation, no implicit state.
- **Tier B** invariants (B1–B9): append-only, no daemon, byte-stable replay, two-step boot, substrate handles concurrency, goals require verifiers.
- **Tier C** aesthetics (C1–C7): find the essential dimension; don't fight, stand on top; geometry > size; cross the boundary; minimal interaction; metaphor everywhere; no churn.
- **Tier D** discipline (D1–D5): standard library only; zero comments unless WHY non-obvious; no TODO/placeholders/half-implementations; no backwards-compatibility shims; no "done" without verification.
- **Tier E** anti-patterns (E1–E9): no derived-as-truth; no state directories beside fragments; no editing past fragments; no kind enumeration; no inventing substrate; no SaaS wrappers; no size-based file splits; no chat-only context; no goals without verifiers.

All five tiers ship as `kind: principle` fragments in every adoption.
`render --for-agent` prepends them at every agent boot.

### Reference implementation

| Component | Lines | Role |
|---|---:|---|
| `tools/sula_vector/render.py` | 590 | Pure-function renderer. 8 views: list, digest, progress, thread, family, goals, principles, changes-summary. |
| `tools/sula_vector/migrate.py` | 449 | Idempotent migrator from legacy Sula projects. |
| `tools/sula_vector/skills/verifier-shell.py` | 122 | Goal verifier via shell commands. |
| `tools/sula_vector/skills/scheduler.py` | 145 | Cadence-tick emitter for recurring intents. |
| `tools/sula_vector/skills/llm-dispatcher.py` | 168 | Routes intents to a configured executor command (LLM CLI, API call, etc.). |
| `tools/sula_vector/AGENTS.md` | 99 | Host operating protocol template. |
| `docs/sula-vector-convention.md` | 422 | Authoritative convention spec. |
| `tools/sula_vector/tests/test_sula_vector.py` | 539 | 34-test stdlib unittest suite. |

Total tooling surface: ~2530 lines. Standard library only. No third-party
dependencies. No daemon, no kernel directory, no cache-as-truth.

### Host operating protocol (in AGENTS.md)

1. **At session start** — note ISO time as `session_start`; run `render --for-agent`; treat output as authoritative project context.
2. **Throughout the turn** — append fragments; never edit; no churn.
3. **At end of turn** — run `render --view changes-summary --since <session_start>` and surface the multi-line `[sula]` block to the user.

---

## Verification evidence

| Check | Result |
|---|---|
| Test suite (`tools.sula_vector.tests.test_sula_vector`) | 34/34 PASS, 1.8s |
| `render.py` byte-stable replay (Sula self) | OK, 5849 bytes constant |
| `render.py` byte-stable replay (1terminal) | OK, 4803 bytes constant |
| `migrate.py` idempotence (3rd run = 0 net change) | OK on Sula self (327 fragments) and 1terminal (28 fragments) |
| `verifier-shell.py` end-to-end | Closed real goal; idempotent on second run |
| `scheduler.py` end-to-end | Fired real cadence-tick on backdated intent; skipped fresh intent |
| `llm-dispatcher.py` end-to-end | Dispatched intent with `cat` executor; appended `kind: turn` with body captured; idempotent |
| AGENTS.md host protocol | Installed in Sula self and 1terminal with sentinel; idempotent |

---

## What any project gains by adopting v1.0

1. **Cross-LLM continuity** — same project context works with any model (Kiro, Claude, Codex, Gemini, future models). Switch cost = 0.
2. **Cross-device portability** — folder syncs through git, Drive, Dropbox, or local; any device that reads text files is a workspace.
3. **Append-only project memory** — every decision/fact/goal preserved forever; supersession via refs, never deletion.
4. **Mechanical goal closure** — `done_when` + `verifier_ref` + skill = automatic closure; no human asking "is it done?"
5. **Tier A–E principles enforced at every boot** — no drift in design standards.
6. **Zero install for new agents** — hand a folder path; no SDK, no daemon, no Python package required by readers.
7. **Domain-agnostic** — code projects, governance, client services, creative work — same `render(fragments, conventions)` shape.
8. **byte-stable replay** — reproducible views from the same fragments; auditable.
9. **Skill-based extensibility** — agent superpowers (durable threads, voice, browser, automation) drop in as ~100-line scripts each. Core never grows when capabilities are added.
10. **Visible "感知" via turn-mark** — multi-line `[sula] +N this turn:` block at end of any turn that appended fragments.
11. **No technical-debt accumulation** — append-only means no maintenance burden.
12. **Free fork/branch** — copy the folder = full history; copy a subset = a derivative.

---

## Adoption guide for a new project

```bash
# 1. Make the folder
mkdir -p new-project/fragments

# 2. Drop in AGENTS template + canonical principles
cp /path/to/sula/tools/sula_vector/AGENTS.md   new-project/AGENTS.md
cp /path/to/sula/tools/sula_vector/principles/*.md   new-project/fragments/

# 3. Verify it boots
python3 /path/to/sula/tools/sula_vector/render.py new-project --for-agent
```

That's the entire onboarding. The output of step 3 is what every future
agent (any LLM) reads to gain full project context.

For existing legacy-Sula projects:

```bash
python3 /path/to/sula/tools/sula_vector/migrate.py --project-root /path/to/legacy-project
```

Idempotent. Leaves legacy `.sula/`, `STATUS.md`, and `docs/change-records/`
untouched (preserved for rollback).

---

## Convention freeze and semantic versioning

- **v1.x** — convention is **frozen**. Existing fragment files written against v1.0 continue to parse, and keep the same meaning, across all v1.x releases. The freeze covers fragment validity and semantics, not the exact bytes of a rendered view: a view that loses live state is a defect and gets fixed.
- **v1.x.y minor releases** may add: new views, new recommended kinds, new skills, new optional frontmatter fields. They will not invalidate existing fragments.
- **v2.0** would only ship if a previously-valid fragment file would no longer parse. There is no current plan for v2.0.

---

## Known limitations (acknowledged, not blockers)

- `llm-dispatcher` ships with a generic shell-executor contract. Wiring to a specific LLM provider (Claude CLI, Codex CLI, OpenAI API, etc.) is the operator's choice — Sula stays provider-agnostic by design.
- The reference renderer's frontmatter parser handles the YAML subset Sula uses (scalars, inline lists, block lists, quoted strings, booleans). Full YAML 1.2 is intentionally not supported; if a project needs it, write fragments with the supported subset.
- No remote sync layer is bundled. Sula uses whatever substrate the project already has (git/Drive/Dropbox/local). This is a feature (B7), not a gap.

---

## Operating Sula Vector going forward

- The convention is finished. **Do not modify it casually.**
- New capabilities are skills. **Add to `tools/sula_vector/skills/`, do not bloat `render.py`.**
- The principles are immutable. **To revise one, append a `kind: decision` whose `refs` includes the principle's id.**
- The substrate handles storage and concurrency. **Sula does not.**

---

## Acknowledgement

This release is the result of a directed dimension-shift exercise: the
predecessor (Sula 0.18.x, ~945 KB single Python file with 12 parallel state
directories) was distilled to its essential dimension — an ordered folder
of typed fragments rendered by a pure function. The same shape covers code
projects, governance projects, client-service projects, and creative
projects. What was 30+ subcommands and a dozen overlapping subsystems is
now one verb (`append`) and one function (`render`).

Three orders of magnitude smaller. Strictly more capable in the dimensions
that matter (cross-LLM, cross-device, byte-stable, principle-enforced). And
it ships with the discipline to keep it that way.

— v1.0
