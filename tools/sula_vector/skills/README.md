# Sula Vector — Skills

Skills are small, independent programs that extend a Sula vector with
reusable capabilities: verifiers, dispatchers, voice transcription, browser
drivers, schedulers, refresh adapters, anything. Each skill is a standalone
script. Together they form the "Superpowers" layer that sits **outside** the
core convention so that core stays minimal and skills stay removable.

## Contract

Every skill must:

1. Take `--project-root <path>` as its required argument.
2. Read fragments from `<project-root>/fragments/`.
3. Filter to fragments it cares about (by `kind`, `refs`, `tags`, etc.).
4. Do its work (call an LLM, run a test, fetch a URL, transcribe audio,
   refresh a provider, etc.).
5. Append new fragments to `<project-root>/fragments/` following the
   convention (filename `<ISO-8601-time-Z>--<slug>.md`, required frontmatter
   `id` / `time` / `kind`).
6. Exit cleanly.

Skills must not:

- Maintain hidden state outside fragments (B2)
- Edit or delete past fragments (B1)
- Add a state directory beside `fragments/` (E2)
- Require a runtime daemon (B4)
- Re-implement what the substrate already does (E5)
- Wrap the project in a SaaS-shaped registry/orchestration layer (E6)

## Discoverability

The "registry" of available skills is `ls tools/sula_vector/skills/`. There
is no manifest, no plugin descriptor, no version negotiation. A skill joins
the registry by virtue of existing in this folder.

A project may optionally record which skills it actively uses by appending a
`kind: skill` fragment with fields like:

```
---
id: <ISO-time>--skill-<name>
time: <ISO-time>
kind: skill
recipe: tools/sula_vector/skills/<name>.py
config:
  key: value
consumes: [intent, goal]
produces: [verification-fact]
---
Reason this project enables <skill name>.
```

This fragment is documentation only. It does not enable or gate anything.

## Invocation

Skills are invoked by whichever scheduler your substrate already provides:

- a human running the script directly
- cron / launchd / systemd timer
- a git pre-push hook
- a file-system watcher
- another agent (Claude / Codex / Gemini) reading recent intents and dispatching

Sula does not start, schedule, or supervise skills. That is correctly the
substrate's job (Tier B7).

## Built-in examples

| skill | what it does |
| ----- | ------------ |
| `witness.py` | Mechanical evidence. Scans the project folder, diffs against the state folded out of prior `kind: witness` fragments, appends one witness fragment recording path + content hash for every added/changed/removed file. Records `commit`/`branch` and the commits since the last witness on git substrates; emits one `kind: artifact` fragment per new document. Silent when nothing changed. |
| `verifier-shell.py` | Runs a shell command as a goal verifier. Reads goals whose `verifier_ref` is `shell:<command>`, runs the command, appends a `kind: verification-fact` with `passed: true/false`. |
| `scheduler.py` | Fires `kind: cadence-tick` when a recurring intent's interval has elapsed. |
| `llm-dispatcher.py` | Routes intents carrying `executor_command` to a configured shell executor and captures stdout as a `kind: turn`. |

`witness.py` is the one skill that changes the protocol's shape: with it
installed, evidence stops depending on an agent choosing to describe what it
did. Wire it once with `../hooks/install.py`.

## Adding a new skill

Drop a new script into this directory. Follow the contract above. Done.

If you find yourself wanting a feature in the core renderer, ask: can it be
a skill instead? Most things can. Keeping the core minimal and skills
plentiful is the architectural goal.
