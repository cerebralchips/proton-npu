# Working on Proton NPU

Read `README.md` for the workflow and `docs/status.md` for measured results and
limitations. This directory owns the integration lab. `upstream/ara` is a pinned,
ignored source checkout with its own matched PULP CVA6 dependency. Source pins
are in `sources.lock.json` and upstream `Bender.lock`.

On this Mac use `./scripts/ara`. The ARM64 Ubuntu Lima VM mounts this repository
at `/ara-workspace`. Tools execute in Linux. New installations use the `proton-npu`
VM; the earlier `cva6` VM remains supported. Read `docs/environment.md` for setup.
Ara's host compiler is native ARM64 Clang; the application compiler is the
RISC-V wrapper at `$LLVM_INSTALL_DIR/bin/clang` inside the guest environment.

`scripts/lab/run.py` uses real CVA6 + Ara RTL, with two lanes and VLEN=2048. Preserve
that baseline when introducing another configuration. Ara's ideal dispatcher is
a separate experiment; it does not establish execution on the combined CPU.

Keep runs serial: upstream app objects and generated linker files are shared.
The wrapper acquires a guest file lock. Build and waveform models have separate
directories. Begin with at most four compile jobs on this 16 GiB Mac.

For program changes use `examples/<app>/main.c`, then `./scripts/ara run <app>`.
For CPU/integration changes also run `./scripts/ara smoke`. Check actual RTL
completion, exit status, and self-check results. Simulator timeout can return
zero upstream, so the success marker and cycle count are required as well.

Our Spike comparison checks application results from separate RTL/Spike runtime
ELFs. It is not a lockstep or instruction-trace comparison. A selected smoke
suite is not complete ISA conformance. Preserve failed logs and report limitations.

Keep downloads, builds, and waveforms out of version control. Each run records
evidence under `artifacts/`; update `docs/status.md` after measured changes.
Capture necessary upstream changes as reviewable patches rather than hiding
edits in dependency checkouts. Avoid blanket cleaning of the shared workspace.

The repository skill is `.agents/skills/ara-development/SKILL.md`.

For matrix changes read `docs/matrix-design.md` and `docs/matrix-running.md`.
Owned RTL is in `hardware/matrix`; upstream Ara/CVA6 changes are reproducible
patches. `./scripts/ara matrix` gates the combined ELF on independent unit checks
and reconciles retired custom instructions with command/completion counts.
`matrix-wave` additionally checks actual FST tile contents. Run `matrix-smoke`,
`matrix-negative`, and the baseline `smoke` after CPU integration changes.
Preserve the custom-1 opcode: custom-0 is used by CVA6 FENCE.T. Preserve slot-0
dispatch and valid/ready load/store accounting. Do not remove assertions or count
speculative issue as completed execution. No HTML model is validation evidence.

For publication/documentation changes run `python3 tests/repository/check.py`.
Keep third-party notices and portable verification records. Never commit ignored
upstream clones, personal paths, credentials, simulator binaries or raw waveforms.
