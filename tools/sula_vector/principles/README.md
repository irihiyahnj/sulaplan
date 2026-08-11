# Sula Vector — Canonical Principles

Five `kind: principle` fragments covering the full Tier A–E enforcement set.
Every Sula vector adoption ships with these in its `fragments/` folder.

## Adopt

From a new project:

```bash
mkdir -p my-project/fragments
cp tools/sula_vector/AGENTS.md my-project/AGENTS.md
cp tools/sula_vector/principles/*.md my-project/fragments/
```

After this:

- `python3 tools/sula_vector/render.py my-project --for-agent` will prepend
  every Tier A–E principle to the boot context.
- `python3 tools/sula_vector/render.py my-project --view principles` lists
  them in canonical order.

## Modifying a principle

Principles obey the same convention as everything else: append-only. Do not
edit or delete a principle fragment. To change one, append a
`kind: decision` fragment with `refs: [<principle-id>]` describing the
supersession. The supersession trail stays visible in every render.
