// SPDX-License-Identifier: Apache-2.0
.section .text
.global rvtest_init
rvtest_init:
  li t0, 0x1800
  csrs mstatus, t0
  fence iorw,iorw
  csrwi 0x7c1, 0
  fence iorw,iorw
  ret
