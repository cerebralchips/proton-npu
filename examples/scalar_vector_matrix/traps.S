// SPDX-License-Identifier: Apache-2.0
.section .text
.global rvtest_init
rvtest_init:
  // Use upstream's startup hook to run this bare-metal test in machine mode.
  // Its default startup selects user mode; privileged guard tests need M mode.
  li t0, 0x1800
  csrs mstatus, t0
  ret
.balign 4
.global matrix_test_trap
matrix_test_trap:
  addi sp, sp, -32
  sd t0, 0(sp)
  sd t1, 8(sp)
  sd t2, 16(sp)
  csrr t0, mcause
  li t1, 2
  beq t0, t1, 1f
  la t1, trap_error
  sw t0, 0(t1)
1:
  la t1, trap_count
  lw t2, 0(t1)
  addi t2, t2, 1
  sw t2, 0(t1)
  csrr t0, mepc
  addi t0, t0, 4
  csrw mepc, t0
  ld t0, 0(sp)
  ld t1, 8(sp)
  ld t2, 16(sp)
  addi sp, sp, 32
  mret
