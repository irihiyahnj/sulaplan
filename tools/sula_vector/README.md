# Sula Vector

A pure-function project memory layer: a folder of typed text fragments
plus a tiny renderer.

- Spec: [`../../docs/sula-vector-convention.md`](../../docs/sula-vector-convention.md)
- Renderer: [`render.py`](render.py)
- AGENTS.md template: [`AGENTS.md`](AGENTS.md)
- Worked example: [`example/`](example/)

The same shape works for code projects, governance projects, client-service
projects, and creative projects. No daemon, no kernel directory, no cache as
truth.

## Quickstart

Initialize a new project:

```bash
mkdir -p my-project/fragments
cp tools/sula_vector/AGENTS.md my-project/AGENTS.md
```

Append a fragment:

```bash
NOW=$(python3 -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ"))')
cat > "my-project/fragments/${NOW}--decision-start.md" <<EOF
---
id: ${NOW}--decision-start
time: $(python3 -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))')
kind: decision
tags: [bootstrap]
---
Adopted Sula vector convention.
EOF
```

Render a view:

```bash
python3 tools/sula_vector/render.py my-project --for-agent
python3 tools/sula_vector/render.py my-project --view digest
python3 tools/sula_vector/render.py my-project --view goals
python3 tools/sula_vector/render.py my-project --view progress --json
python3 tools/sula_vector/render.py my-project --view thread --thread chief-of-staff
python3 tools/sula_vector/render.py my-project --view family --family hospital-acme-intake
```

## Substrates

The folder works the same way regardless of where it lives:

- **git repository** — commit fragments alongside code; history comes from git
- **Google Drive / Dropbox / OneDrive** — edit on any device with sync
- **plain folder** — copy or zip to share

## Re-implementing render

The reference renderer is standard-library Python only and under 500 lines.
Re-implement it in any language; given the same fragments and conventions, the
output is byte-stable.

## Try the example

```bash
python3 tools/sula_vector/render.py tools/sula_vector/example --for-agent
python3 tools/sula_vector/render.py tools/sula_vector/example --view goals
python3 tools/sula_vector/render.py tools/sula_vector/example --view progress
python3 tools/sula_vector/render.py tools/sula_vector/example --view family --family hospital-acme-intake
python3 tools/sula_vector/render.py tools/sula_vector/example --view thread --thread chief-of-staff
```
