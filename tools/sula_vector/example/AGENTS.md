# AGENTS.md — example Sula vector

This example folder is itself a Sula vector. It mixes a code refactor and a
client-services engagement to demonstrate that both flow through the same
fragments.

Run from the repo root:

```bash
python3 tools/sula_vector/render.py tools/sula_vector/example --for-agent
python3 tools/sula_vector/render.py tools/sula_vector/example --view goals
python3 tools/sula_vector/render.py tools/sula_vector/example --view progress
python3 tools/sula_vector/render.py tools/sula_vector/example --view family --family hospital-acme-intake
python3 tools/sula_vector/render.py tools/sula_vector/example --view thread --thread chief-of-staff
```

See `../AGENTS.md` for the full convention agents should follow.
