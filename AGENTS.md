<!-- sula-vector -->
# AGENTS.md — Sula Vector

This project's truth lives in `fragments/` as an append-only folder of typed
text files. Every view — status, progress, agent context, audit trail — is
`render(fragments, conventions)`.

## Highest rule (Tier A)

> A project's truth is an ordered, append-only folder of typed fragments.
> Every view is `render(fragments, conventions)`.
> No mutation. No implicit state. No truth outside this convention.
>
> If anything else conflicts with this rule, this rule wins.

Tier B (invariants), C (aesthetics), D (discipline) and E (anti-patterns) ship
as `kind: principle` fragments inside this project. `render --for-agent`
prepends them to every boot. `render . --view principles` prints them in full.

## Boot — two steps (B6)

1. Note the current ISO-8601 UTC time as your `session_start`.
2. Run and read:

```bash
python3 tools/sula_vector/render.py . --for-agent
```

That output is authoritative project context. Nothing else is required —
no install, no network, no daemon.

## Three lanes

Every fragment falls into one of three lanes. `kind` stays a free-form string
(B3); the lane is a render-time projection, not a validated enum.

| lane | question | who supplies it |
| --- | --- | --- |
| `judgment` | **why** — decisions, corrections, assessments, principles | you, deliberately |
| `evidence` | **what** — files produced, commits made, external facts | `skills/witness.py`, mechanically |
| `direction` | **where to** — goals and intents, each closable | you, with a verifier |

The division is the whole protocol: **you are responsible for judgment, the
runtime is responsible for evidence.** Do not narrate mechanical facts by
hand — witness already has them, with hashes.

## During the turn

Record a judgment whenever you choose a direction, revise one, correct a past
claim, or assess state. One append per judgment (C5):

```bash
python3 tools/sula_vector/note.py . --kind decision --title "<one line>" "<why>"
python3 tools/sula_vector/note.py . --kind correction --supersedes <id> "<what was wrong>"
python3 tools/sula_vector/note.py . --kind goal --title "<outcome>" \
  --done-when "<condition>" --verifier "shell: <command>" "<context>"
python3 tools/sula_vector/note.py . --kind fact --closes <intent-id> "<what closed it>"
```

`note.py` derives `id` and `time` from the clock, rejects unknown `--refs` /
`--closes` / `--supersedes` targets, and refuses a goal without a verifier.
Never hand-write a fragment file: a wrong id, a wrong timestamp, or a dangling
reference should be unrepresentable, not merely detectable.

## Never

- Edit or delete a past fragment (B1, E3). Append a `correction` that names it
  in `--supersedes` instead.
- Append when nothing meaningful changed (C7).
- Declare a goal without a verifier (B9, E9).
- Add a state directory, cache, index, or daemon beside `fragments/` (B4, E1, E2).

## End of turn

If you appended anything, show the user the mark:

```bash
python3 tools/sula_vector/render.py . --view changes-summary --since <session_start>
```

Display the full multi-line `[sula] +N this turn:` block. If the output is
`[sula] no changes`, display nothing (C7).

If the mark ends with `! N file change(s) witnessed, no judgment recorded`, the
turn changed files and left no why behind. Append the missing judgment before
you finish — witness has the what, and only you have the reason. The same
notice appears in the next agent's boot under `## Unexplained change`, so the
omission is inherited, not forgotten.

Before claiming a task is done (D5), the vector must be structurally clean:

```bash
python3 tools/sula_vector/render.py . --view doctor   # must exit 0
```

## Views

```bash
python3 tools/sula_vector/render.py . --for-agent            # boot context
python3 tools/sula_vector/render.py . --view journal         # day by day: decided / produced
python3 tools/sula_vector/render.py . --view effective       # judgments in force + supersession trail
python3 tools/sula_vector/render.py . --view goals           # goals + verification status
python3 tools/sula_vector/render.py . --view doctor          # structural integrity
python3 tools/sula_vector/render.py . --lane evidence --view list
```

## Mechanical capture

```bash
python3 tools/sula_vector/hooks/install.py --project-root .   # once per project
python3 tools/sula_vector/skills/witness.py --project-root .  # or run by hand
```

The installer wires whatever the substrate already offers, and names the host
each trigger actually reaches: a git `post-commit` hook, a Kiro CLI agent
config (`agentSpawn` injects this boot, `stop` witnesses the turn), a Kiro IDE
hook, and on a folder or Drive substrate a launchd timer on macOS or the cron
line to paste. Sula never schedules anything itself (B7).

The Kiro CLI agent is written but not activated: a custom agent replaces the
built-in default agent's prompt, which is not a change to make on someone's
behalf. Activate it with `kiro-cli settings chat.defaultAgent sula`.

## Adopt into a new project

```bash
mkdir -p new-project/fragments
cp -r tools/sula_vector new-project/tools/sula_vector
cp tools/sula_vector/AGENTS.md new-project/AGENTS.md
cp tools/sula_vector/principles/*.md new-project/fragments/
python3 new-project/tools/sula_vector/hooks/install.py --project-root new-project
```

Works the same for a code repository, a company folder of documents on Drive,
or a personal project. The full convention is
`docs/sula-vector-convention.md`.
