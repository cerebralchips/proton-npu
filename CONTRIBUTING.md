# Contributing to Proton NPU

Start with the [README](README.md), [HTML architecture guide](docs/index.html),
[design contract](docs/matrix-design.md), and [AGENTS.md](AGENTS.md).
Target the `hardware` branch. Keep changes focused and preserve passing evidence.

## Development workflow

1. Provision the pinned environment and run `./scripts/ara doctor`.
2. Reproduce the baseline with `./scripts/ara matrix` before changing hardware.
3. Edit owned source under `hardware/`, applications under `examples/`, or tests
   under `tests/`. Turn dependency edits into reviewable patches under `patches/`;
   an edit only in ignored `upstream/` will not reach other contributors.
4. Keep an independent software arithmetic reference. Never adjust expected data
   solely to match RTL output. Regenerate workload constants with
   `python3 tests/matrix/workload.py examples/scalar_vector_matrix/workload.h`.
5. Run checks appropriate to the change, and attach the resulting run identifiers
   and concise results to the review. Keep raw generated files out of Git.

## Required checks

| Change | Verification |
| --- | --- |
| Documentation / packaging | `python3 tests/repository/check.py`; inspect HTML on desktop/mobile |
| Bare-metal program | Run that application and check actual RTL completion and results |
| Matrix RTL | `matrix-unit`, `matrix`, `matrix-wave` |
| CPU / Ara / integration | Above, then `matrix-smoke`, `matrix-negative`, `smoke` |

Every hardware command is `./scripts/ara COMMAND`. Run them serially: upstream
application objects are shared. A simulator return code of zero is insufficient;
our wrapper also requires completion markers, positive cycle counts, self-checks,
and (for the combined ELF) retired-instruction/command reconciliation.
The negative suite passes only when deliberate application failures are rejected.

The lightweight GitHub workflow checks repository packaging and documentation. It
does not run the full RTL suite. Historical verification snapshots identify their
source hashes and are not a substitute for rerunning changed hardware.

## Documentation

Edit static HTML and SVG directly in `docs/`; no bundler or CDN is required.
Open `docs/index.html` locally, or run `python3 -m http.server 8000` and browse
`http://localhost:8000/docs/`. Keep the Markdown index useful on GitHub as well.
The PE explorer is a teaching model; never cite it as proof of RTL execution.

Preserve upstream license notices and update [THIRD_PARTY.md](THIRD_PARTY.md) when
adding a dependency. Original contributions are Apache-2.0 unless a file's
existing license requires otherwise.
