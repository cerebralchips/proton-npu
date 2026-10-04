# Lesson: one C program, scalar and vector hardware

Start in the Mac terminal:

```bash
cd proton-npu
./scripts/ara vm-start
./scripts/ara doctor
./scripts/ara hello
./scripts/ara run
```

`vm-start` starts the Linux build machine. `doctor` checks the pinned versions.
`hello` exercises startup, memory, console output, and termination. `run` compiles
and executes [scalar_vector/main.c](../examples/scalar_vector/main.c). A hardware
model is built automatically if needed; changing only C code reuses that model.

## Follow the program

1. Scalar loops initialize `a[i] = i` and `b[i] = 2*i + 1`.
2. `vector_add()` asks hardware how many 32-bit elements it can process now,
   loads that many elements, adds them, and stores them.
3. Scalar code checks each answer and verifies that stores did not modify
   elements outside the requested range.
4. `vector_sum()` reduces the result array to one number, returned to a scalar
   register. Scalar code verifies the sum.

For seven elements:

```text
A = [0, 1, 2, 3, 4, 5, 6]
B = [1, 3, 5, 7, 9, 11, 13]
C = [1, 4, 7, 10, 13, 16, 19]
sum(C) = 70
```

The program repeats this for 0, 1, 7, 63, 64, 65, 127, 128, 129, and 257 elements.
The final sum for 257 is 98,945. Each case checks memory and its reduction.
The runner independently checks printed sums against `(3*n*n - n)/2`.

## What the RVV names mean

| C intrinsic / term | Meaning |
| --- | --- |
| `__riscv_vsetvl_e32m1(n)` | Set the active length for 32-bit elements and one-register groups; return how many elements to process |
| `__riscv_vle32_v_u32m1` | Load unsigned 32-bit elements into a vector register |
| `__riscv_vadd_vv_u32m1` | Add corresponding elements of two vectors |
| `__riscv_vse32_v_u32m1` | Store active vector elements to memory |
| `__riscv_vredsum_vs_u32m1_u32m1` | Reduce active elements into a sum with a starting value |
| `__riscv_vmv_x_s_u32m1_u32` | Move the scalar result out of the vector register |
| VLEN=2048 | Each architectural vector register stores 2,048 bits |
| SEW=32, LMUL=1 | One register holds up to 64 active 32-bit elements |
| Two lanes | Two physical groups of execution hardware; not two CPUs |

For arrays larger than a register, the loop advances pointers by the returned
`vl` and repeats. Always use the returned length; do not hard-code how hardware
splits an intermediate array length into chunks.

Scalar reference loops have automatic vectorization disabled, while explicit
intrinsics still generate RVV. Inspect the saved `program.dump` to see the actual
instructions. The compiler chooses register numbers; C variables are not fixed
hardware registers.

## Inspect execution evidence

```bash
RUN=$(./scripts/ara latest run)
cat "$RUN/result.json"
cat "$RUN/rtl.log"
cat "$RUN/spike.log"
```

Spike is a software model of the instruction set; Verilator runs the hardware
description. Their startup and console environments differ, so this lab builds
separate ELFs and compares application results. It does not compare their cycle
counts or claim a complete instruction-by-instruction match.

The passing demo reports 57,632 total RTL cycles on the initial baseline. That
includes startup, initialization, checking, and printing; it is not a vector
kernel benchmark or a prediction of physical chip frequency.

## See a real failure

```bash
./scripts/ara run --inject-failure
```

This deliberately asks the final reduction to equal 98,946 instead of 98,945.
The RTL program reports a failure, and the wrapper returns nonzero. Its artifact
folder preserves the source, flags, and failing log. It is an expected failure
exercise, not a passing workload.

```bash
./scripts/ara run --max-cycles 20
```

This stops simulation before the program completes. The upstream simulator can
return zero on timeout; our wrapper rejects the missing success marker.

Return to the ordinary example with `./scripts/ara run`. Follow
[the waveform lesson](waveforms.md) to see instructions and result transfers.
