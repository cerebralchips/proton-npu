---
name: ara-development
description: Build, run, inspect, and extend this Ara + CVA6 bare-metal RTL simulation lab on the Mac's ARM Linux VM. Use for its RVV C programs, waveforms, toolchain failures, or hardware integration changes.
---

# Ara development

Read the lab's `AGENTS.md`, `README.md`, and `docs/status.md`. Paths below are
relative to the lab root, not this skill directory.

Use `./scripts/ara` from the Mac. In its Linux shell, source
`scripts/lab/env.sh` before manual tools. The host checkout path has spaces;
upstream Makefiles run at the space-free `/ara-workspace/upstream/ara`.

For a C workload, put source under `examples/<app>/main.c`. The runner copies it
into upstream's app structure and reuses its startup code and memory map. Start
with `examples/scalar_vector/main.c` for explicit RVV intrinsics and a scalar
oracle. Its scalar loops are compiled with automatic vectorization disabled.

Use `./scripts/ara run` for the teaching demo, `hello` for runtime bring-up,
`smoke` for the selected scalar/vector regression, and `wave` for an FST run.
Follow `docs/waveforms.md` for inspected signal paths and the relation between
instruction dispatch, vector completion, and architectural results.

On failure, inspect the run's `result.json` and first failing compile or execution
log. A simulator zero exit code without its successful completion marker is not
a pass. Do not drop checks or modify expected results to hide a mismatch.

Hardware comes from upstream Ara's locked dependency set, including its PULP
CVA6 fork. The older sibling `cva6` lab has different tools and integration.
Reproduce a failure on the pinned baseline before porting between these trees.
Preserve required dependency patches and record additional ones in the lab.

Spike uses a different startup/runtime ELF. Compare the demonstrated application
results; do not describe this as full instruction or register-trace equivalence.
Use an explicit future milestone for Linux or IREE work; this baseline does not
claim either has been brought up.
