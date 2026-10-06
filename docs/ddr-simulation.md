# SRAM and simulated DDR

The optional `PROTON_DDR` target adds a **4 GiB functional external-memory model**
to the actual CVA6 + two-lane Ara + matrix SoC in Verilator. The original target
remains selectable. This is a simulation target, not a synthesizable DDR
controller/PHY or a calibrated DDR performance model. Software deployment is maintained
in the sibling [proton-sdk](https://github.com/cerebralchips/proton-sdk) repository.

| Region | Start | Last byte | Capacity | Attributes |
| --- | --- | --- | --- | --- |
| Internal SRAM | `0x80000000` | `0x80ffffff` | 16 MiB | Existing cached, executable main memory |
| External DDR model | `0x100000000` | `0x1ffffffff` | 4 GiB | Uncached, idempotent data memory; no atomics |
| UART / control / matrix | `0xc0000000` / `0xd0000000` / `0xe0000000` | Existing peripheral ranges | Unchanged | MMIO |

The DDR target tightens the SRAM decode to its installed size. The control
register reports `0x81000000` as the SRAM end, so upstream startup places the stack
in physical SRAM. The legacy target's larger, aliasing decode remains unchanged.
The generic upstream linker still advertises 32 MiB: applications must stay within
the 16 MiB SRAM contract. The address-aware loader rejects segments outside the
actual registered regions. The SDK provides a separate DDR linker/profile; see its
[DDR deployment guide](https://github.com/cerebralchips/proton-sdk/blob/main/docs/ddr.md).
That profile places packed projection weights in DDR and keeps working memory
in SRAM. SDK numerical evidence is maintained in that repository.

## Run

```sh
./scripts/ara ddr-test
```

This acquires the usual hardware lab lock, applies the reproducible patch stack,
builds `build-ddr-wave`, runs the AXI unit and loader rejection checks, then runs
the bare-metal test twice: latency 1/stall 0 and latency 7/stall 3. The second run
records FST and independently checks it. The existing scalar/vector/matrix
combined workload also runs on the DDR-enabled simulator.

`./scripts/ara ddr-build` builds only; `./scripts/ara ddr-unit` runs the focused
AXI unit gate. `./scripts/ara smoke`, `matrix-smoke`, and `matrix-negative` retain
their existing targets. Start with four build jobs on the supported Mac/Linux VM.

The memory model uses sparse 64-bit words. Unwritten locations read as zero;
host allocation grows with touched/preloaded words rather than eagerly allocating
4 GiB. Reset clears protocol state and counters, retaining external contents.

`+ddr_latency=N` delays the response after accepting a memory request;
`+ddr_stall=N` adds a cooldown before another request can be accepted. At the
bridge's sampling edges, a latency setting of 7 produces an 8-cycle
request-to-response handshake interval. These settings exercise handshakes and
stalls; they do not model refresh, banks, row hits, bus turnaround or DDR bandwidth.

Use `--load-elf=FILE` for ELF segments spanning SRAM and DDR. The loader's physical
address/region arithmetic is 64-bit; the test preloads and reads back data above
4 GiB and in the final DDR word. Attached `=FILE` syntax avoids the upstream
multi-pass command parser's argument permutation issue with Verilator plusargs.

## Checks and evidence

The [bare-metal test](../examples/ddr_memory/main.c) writes every sample before
reading it back, so address aliasing cannot be hidden by an immediate readback.
It covers:

- One location in every MiB: 4,096 locations across 4 GiB, with two complementary
  address-derived patterns, plus every word-address bit and both endpoints.
- SRAM/DDR isolation, including addresses with identical low 32 bits.
- Walking ones and zeros on all 64 data bits.
- Byte, halfword and word stores at the final DDR word, including the last byte.
- Ara vector loads/stores, bursts and a 67-element tail, checked by scalar code.
- Three unmapped boundary reads and writes, with AXI error verification in FST.

This is **sampled address-space validation, not a read/write sweep of all 4 GiB**.
The independent AXI unit additionally holds R/B responses under backpressure,
skews AW/W arrival, checks IDs and burst termination, checks zero strobes and
out-of-range errors, and verifies reset/content retention.

Each run keeps its ELF, source/simulator hashes, logs and result JSON in
`artifacts/`. The traced run also contains `sim.fst`, a compact `ddr.vcd`,
`ddr-transactions.csv` and `ddr-wave-check.json`. The checker reconstructs memory
from initial ELF contents and accepted writes, checks every memory read and its
latency, and reconciles AXI response IDs, burst termination and decode errors.

## Dense vector sweeps

The [dense sweep program](../examples/ddr_sweep/main.c) adds two tests beyond the
sampled sanity checks. Both initialize the **entire selected range first** with
address-derived data using scalar stores, transfer every word using explicit RVV loads/stores, and
check every output word against an independent scalar calculation. Automatic
compiler vectorization is disabled for that scalar oracle.

- `direct`: vector load from DDR, XOR the data, vector store back to DDR, then
  scalar readback of the entire output. The changed pattern detects missing stores.
- `staged`: vector copy DDR to SRAM, scalar check of the SRAM chunk, vector load
  from SRAM, XOR and vector store back to DDR. Reuse the SRAM buffer until DDR
  is exhausted, then scalar-check the entire DDR output.

```sh
./scripts/ara ddr-sweep-smoke
./scripts/ara ddr-sweep --mode direct --bytes 0x10018
./scripts/ara ddr-sweep --mode staged --bytes 0x40018 --stage-bytes 0x1000
# A bounded range ending at the last byte of DDR, with delayed responses and FST:
./scripts/ara ddr-sweep --bytes 0x10018 --offset 0xfffeffe8 --latency 7 --stall 3 --trace
```

`ddr-sweep-smoke` exercises both modes at the beginning and end of DDR, with
65,560-byte ranges (64 KiB + 24 bytes), 4 KiB SRAM chunks, vector/chunk tails,
and guards around the selected DDR and SRAM ranges. High-address runs use
latency 7/stall 3 and independently checked FST. These traces must contain exactly
two reads and two writes for **each** selected DDR word, with the correct patterns,
response IDs and delay. Deliberately corrupting the last input word must fail both
tests. Additional 262,168-byte runs (256 KiB + 24 bytes), without tracing, provide
a full-sweep runtime estimate. The suite records all runs in its summary JSON.
The [6 October measurement](../verification/2026-10-06/ddr-sweeps.json) projects
about **99 hours direct / 152 hours staged**, without tracing, at latency 1/stall 0.
These include initialization, transfers and complete scalar verification.

The SRAM staging reservation is `0x80100000..0x80efffff` (**14 MiB**). The bottom
and top 1 MiB of the installed 16 MiB SRAM are reserved for code/data and stack;
the runner rejects a program ELF that overlaps the staging area/guard. Bounded
tests reuse 4 KiB at the low and high ends of that reservation. A full run defaults
to 14 MiB chunks, with a short final chunk. This is a software scratch buffer,
not an added DMA engine or automatic cache policy.

Explicit full-range commands are available, but the bounded suite does **not**
establish that all 4 GiB have passed:

```sh
# For a sufficiently large simulation host; 7-day wall watchdog per test.
./scripts/ara ddr-sweep --mode direct --full --timeout 604800
./scripts/ara ddr-sweep --mode staged --full --timeout 604800
```

Every selected byte is covered by aligned 64-bit accesses; sizes/offsets must be
multiples of eight. Subword strobes remain covered by `ddr-test`. A full sweep
writes/reads 4 GiB four times in DDR (16 GiB of DDR traffic), plus SRAM traffic for
the staged test. It retains all initialized DDR contents until final verification.
The current simulation backend stores an associative entry per 64-bit word;
full occupancy needs substantially more than 4 GiB of host RAM and exceeds the
standard 8 GiB VM. Use a larger host or change that storage backend to sparse
pages before attempting it on this VM. Reported full-run times are extrapolations;
larger maps, allocation pressure and staging size affect actual time. FST is limited
to bounded ranges to keep waveforms manageable. The runner omits the upstream
signed-32-bit cycle-limit option for long runs and retains the wall-clock watchdog.

### Unresolved vector initialization stall

An initial version generated input using repeated `vid.v`, `vadd.vx`, `vxor.vx`
and `vse64.v` into the same vector register. That sequence stalled after two
completed 256-byte stores; a 20,000-cycle FST shows the DDR model idle with
`mem_req=0`, `mem_gnt=1`, no pending response, and a vector store awaiting operands.
The root cause is **not resolved**. The transfer tests use scalar initialization,
which also makes their input generation independent of the vector path being tested.
Their pass does not qualify this additional vector producer sequence.

The failing sequence remains available as a diagnostic (the command should fail,
not report a successful verification):

```sh
./scripts/ara ddr-sweep --mode direct --bytes 65560 --vector-init --max-cycles 20000 --trace
```

## Try a timed DDR → SRAM → vector addition → DDR program

The [buffer-add program](../examples/ddr_vector_add/main.c) runs on the actual
CVA6 + Ara RTL. It uses three DDR buffers of unsigned 32-bit integers, and three
small scratch arrays in internal SRAM. For each pass it does the following:

1. Scalar code fills DDR inputs: `A[i] = i + pass`, `B[i] = 2*i + 1`.
   It fills output `C` with deliberately wrong values so missing stores are caught.
2. Vector loads read a chunk of A/B from DDR into vector registers; vector stores
   write those registers into SRAM A/B. **No `memcpy` or DMA is used.**
3. Vector loads read SRAM A/B, `vadd.vv` adds them, and vector stores write SRAM C.
4. Another vector load/store copy moves SRAM C back to DDR C.
5. Repeat these steps with the next chunk, reusing SRAM, until the buffers are done.
6. Scalar loads check **every** DDR output against `3*i + pass + 1`. The program
   also checks that both input buffers and the guard elements are unchanged.

The copies use `vle32.v` / `vse32.v`; the addition uses `vadd.vv`. Operations happen
in vector registers: neither a vector copy nor an addition operates directly
between two memory locations. Fences order the copy/add/copy phases. A chunk is
1,024 elements, so SRAM scratch is about 12 KiB plus guards. Default buffer sizes
leave a three-element final chunk to exercise short vector operations.

From the repository directory on the Mac, first build the simulator outside the
timed experiment (the VM/tools already provisioned for this lab are required):

```sh
./scripts/ara vm-start                     # If the Linux VM is stopped
./scripts/ara ddr-build                    # Reuses an existing up-to-date build
/usr/bin/time -p ./scripts/ara ddr-add      # Small, one-pass example
```

The small example checks 4,099 additions. The measured run passed in **290,915 RTL
cycles**, with Linux `/usr/bin/time -p` reporting **6.38 seconds**. Your time will
vary with host load. Progress and the final result appear live in the terminal:

```text
FLOW: DDR A/B -> SRAM A/B -> vector add -> SRAM C -> DDR C -> scalar check
CHECK 1/1 OK: 4099 results match; inputs and guards intact
RESULT: PASS ddr_vector_add elements=4099 passes=1 checked_outputs=4099
...
Core Test *** SUCCESS *** (tohost = 0)
Executed cycles: 290915
...
SIMULATOR TIME (Linux /usr/bin/time -p):
real 6.38
user 6.33
sys 0.01
```

For an approximately one-hour experiment:

```sh
/usr/bin/time -p ./scripts/ara ddr-add --target-seconds 3600
```

This measures two complete passes first, using **16,387 elements per buffer**,
then chooses a repeat count and runs a new bare-metal program toward one hour.
The three DDR buffers occupy only **196,644 bytes** in total, plus guards. Each
pass changes input A and poisons output C again; this repeats real computation
and checking rather than waiting or sleeping. It is **not** a 4 GiB address sweep.
Calibration prints seconds per pass, the chosen count and the estimated runtime.
The measured two-pass check at this size took **46.78 seconds**; that projects
approximately **154 passes** for one hour. The command measures again rather than
assuming your machine will run at that speed.
This is approximate: host activity, instruction layout and repeat count affect
speed. The outer command includes calibration and compilation, so expect more
than an hour overall. There is a two-hour wall watchdog for the timed simulations.

The outer Mac `time` measures the entire command. For simulator-only time, use
the **Linux `SIMULATOR TIME` block after the final run**, also saved in
`simulator-time.txt`. `real` is elapsed wall time; `user`/`sys` are Linux CPU time.
Neither represents time on a physical Proton chip. `Executed cycles` counts the
clock cycles executed by the simulated RTL. The runner saves the ELF, disassembly,
UART output in `rtl.log`, timing and `result.json` in the printed artifact directory.
Guest `/ara-workspace/artifacts/...` corresponds to `artifacts/...` in this checkout.
Waveforms and per-instruction debug logs are disabled for these timing runs.
In the measured 60-second exercise, calibration chose ten passes; the final
simulator run took **60.28 seconds** and the whole Mac command took **75.81 seconds**.
The Mac `user`/`sys` fields do not include the remote VM's simulator CPU usage;
use the Linux timing block for that breakdown.

Optional shorter repetition and failure demonstrations:

```sh
/usr/bin/time -p ./scripts/ara ddr-add --elements 4099 --target-seconds 60
./scripts/ara ddr-add --elements 67 --inject-failure  # Must return FAIL/nonzero
./scripts/ara ddr-add-test                           # Positive + negative sanity gates
```

The sanity suite also tests delayed DDR responses, repeated passes, buffer tails,
deliberate bad output, and a forced timeout. A PASS requires correct data, all
per-pass checks, RTL successful completion, positive cycle count and successful
process exit. A zero exit code from a timed-out simulator is not accepted.
See [measured evidence](../verification/2026-10-06/ddr-vector-add.json).

This is functional verification of this program and data path on RTL, not proof
of every RTL behavior, physical DDR timing, or AI model correctness. The earlier
optional vector-initialization stall remains open; this program uses scalar
initialization and explicit vector operations for the copies and addition.

## Known CPU error-handling limitation

The pinned CVA6 write-through cache adapter does not propagate ordinary AXI
read/write error responses into architectural load/store access exceptions.
The initial trap-based boundary test exposed this and is retained as a failed
attempt. The SoC crossbar correctly responds with `DECERR` for unmapped addresses;
the final test verifies those responses directly in the waveform and verifies
that rejected writes do not modify valid memory. It does **not** claim CPU
exception handling for those accesses. Applications must obey the memory map.

DDR is deliberately uncached in this first target, ensuring the sanity test
reaches the external-memory path. Cacheable DDR and CPU bus-error propagation
would require separately qualified changes. These results do not establish
formal correctness, physical DDR functionality, timing closure or SDK model
deployment.
