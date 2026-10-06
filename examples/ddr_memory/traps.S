// SPDX-License-Identifier: Apache-2.0
.section .text
.global rvtest_init
rvtest_init:
  li t0, 0x1800
  csrs mstatus, t0
  ret
.balign 4
.global ddr_probe_load
ddr_probe_load:
  .option push
  .option norvc
  ld a0, 0(a0)
  .option pop
  ret
