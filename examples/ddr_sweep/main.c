// SPDX-License-Identifier: Apache-2.0
// Compile twice: direct DDR load/store, or DDR -> SRAM -> DDR.
// Every byte in the selected range is initialized, transferred, and checked.
#include <stdint.h>
#include <stddef.h>
#include <riscv_vector.h>
#include "printf.h"

#ifndef SWEEP_BYTES
#define SWEEP_BYTES 65560UL
#endif
#ifndef SWEEP_OFFSET
#define SWEEP_OFFSET 0UL
#endif
#ifndef STAGED
#define STAGED 0
#endif
#ifndef STAGE_BYTES
#define STAGE_BYTES 4096UL
#endif
#ifndef STAGE_BASE
#define STAGE_BASE 0x80100000UL
#endif
#ifndef INJECT_FAILURE
#define INJECT_FAILURE 0
#endif
#ifndef VECTOR_INIT
#define VECTOR_INIT 0
#endif

#define DDR_BASE UINT64_C(0x100000000)
#define DDR_BYTES UINT64_C(0x100000000)
#define SEED UINT64_C(0xd3c5a709abcd1234)
#define CHANGE UINT64_C(0x96a53cc3f00f5aa5)
#define GUARD UINT64_C(0xdeadbeef76543210)
#define MODE (STAGED ? "staged" : "direct")
_Static_assert(sizeof(uintptr_t) == 8, "A 64-bit address space is required");
_Static_assert(SWEEP_BYTES > 0 && SWEEP_BYTES <= DDR_BYTES && SWEEP_BYTES % 8 == 0,
               "Sweep size must be a nonzero multiple of eight, at most 4 GiB");
_Static_assert(SWEEP_OFFSET % 8 == 0 && SWEEP_OFFSET <= DDR_BYTES - SWEEP_BYTES,
               "Sweep must fit in DDR");
_Static_assert(STAGE_BYTES > 0 && STAGE_BYTES % 8 == 0 && STAGE_BASE % 8 == 0 &&
               STAGE_BASE >= 0x80100000UL &&
               STAGE_BASE + STAGE_BYTES <= 0x80f00000UL,
               "Reserve bottom/top 1 MiB of SRAM for program/stack");

static inline void fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static inline uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value) :: "memory");
  return value;
}
static uint64_t pattern(uint64_t address) { return (address >> 3) ^ SEED; }

// Scalar setup is independent of the vector transfer under test.
__attribute__((noinline)) static void fill(uint64_t *dst, size_t words) {
#if VECTOR_INIT
  // Optional diagnostic: this producer sequence currently stalls on the pinned
  // RTL. Keep it reproducible; ordinary transfer tests use independent scalar setup.
  while (words) {
    size_t vl = __riscv_vsetvl_e64m1(words);
    vuint64m1_t v = __riscv_vid_v_u64m1(vl);
    v = __riscv_vadd_vx_u64m1(v, (uintptr_t)dst >> 3, vl);
    v = __riscv_vxor_vx_u64m1(v, SEED, vl);
    __riscv_vse64_v_u64m1(dst, v, vl);
    dst += vl; words -= vl;
  }
#else
  for (size_t i = 0; i < words; ++i)
    ((volatile uint64_t *)dst)[i] = pattern((uintptr_t)(dst+i));
#endif
}

__attribute__((noinline)) static void copy_xor(const uint64_t *src, uint64_t *dst,
                                               size_t words, uint64_t change) {
  while (words) {
    size_t vl = __riscv_vsetvl_e64m1(words);
    vuint64m1_t v = __riscv_vle64_v_u64m1(src, vl);
    v = __riscv_vxor_vx_u64m1(v, change, vl);
    __riscv_vse64_v_u64m1(dst, v, vl);
    src += vl; dst += vl; words -= vl;
  }
}

__attribute__((noinline)) static int verify(const volatile uint64_t *data, size_t words,
                                            uint64_t ddr_address, uint64_t change) {
  for (size_t i = 0; i < words; ++i) {
    uint64_t expected = pattern(ddr_address + 8*i) ^ change;
    uint64_t actual = data[i];
    if (actual != expected) {
      printf("RESULT: FAIL ddr_sweep mode=%s address=%lx expected=%lx actual=%lx\n",
             MODE, (unsigned long)(ddr_address + 8*i),
             (unsigned long)expected, (unsigned long)actual);
      return 1;
    }
  }
  return 0;
}

int main(void) {
  const uint64_t start = DDR_BASE + SWEEP_OFFSET, end = start + SWEEP_BYTES;
  uint64_t *ddr = (uint64_t *)(uintptr_t)start;
  const size_t words = SWEEP_BYTES / 8;
  volatile uint64_t *before = (volatile uint64_t *)(uintptr_t)(start - 8);
  volatile uint64_t *after = (volatile uint64_t *)(uintptr_t)end;
  printf("DDR_SWEEP mode=%s start=%lx bytes=%lu stage_base=%lx stage_bytes=%lu\n",
         MODE, (unsigned long)start, (unsigned long)SWEEP_BYTES,
         (unsigned long)STAGE_BASE, (unsigned long)(STAGED ? STAGE_BYTES : 0));
  if (start > DDR_BASE) *before = GUARD;
  if (end < DDR_BASE + DDR_BYTES) *after = GUARD;
  fence();
  uint64_t t0 = cycles();
  // Fill the entire selected DDR range before any transfer or readback. Do not
  // reuse/clear DDR storage chunk by chunk: retention and aliasing must be tested.
  fill(ddr, words); fence();
  uint64_t t1 = cycles();
  if (INJECT_FAILURE) {
    ((volatile uint64_t *)ddr)[words - 1] ^= 1;
    fence();
  }
  size_t chunks = 0;
  if (STAGED) {
    uint64_t *stage = (uint64_t *)(uintptr_t)STAGE_BASE;
    volatile uint64_t *stage_before = (volatile uint64_t *)(uintptr_t)(STAGE_BASE - 8);
    volatile uint64_t *stage_after = (volatile uint64_t *)(uintptr_t)(STAGE_BASE + STAGE_BYTES);
    *stage_before = GUARD; *stage_after = GUARD; fence();
    for (size_t off = 0; off < words;) {
      size_t n = words - off;
      if (n > STAGE_BYTES / 8) n = STAGE_BYTES / 8;
      // Guard the short final chunk as well as the complete staging buffer.
      volatile uint64_t *tail = stage + n;
      *tail = GUARD; fence();
      copy_xor(ddr + off, stage, n, 0); fence();
      if (verify(stage, n, start + 8*off, 0)) return 1;
      if (*stage_before != GUARD || *stage_after != GUARD || *tail != GUARD) return 2;
      copy_xor(stage, ddr + off, n, CHANGE); fence();
      off += n; ++chunks;
    }
  } else {
    copy_xor(ddr, ddr, words, CHANGE); fence();
    chunks = 1;
  }
  uint64_t t2 = cycles();
  // Independent scalar calculation and scalar loads check every output word.
  if (verify(ddr, words, start, CHANGE)) return 3;
  if ((start > DDR_BASE && *before != GUARD) ||
      (end < DDR_BASE + DDR_BYTES && *after != GUARD)) return 4;
  fence();
  uint64_t t3 = cycles();
  printf("SWEEP_CYCLES init=%lu transfer=%lu verify=%lu\n",
         (unsigned long)(t1-t0), (unsigned long)(t2-t1), (unsigned long)(t3-t2));
  printf("RESULT: PASS ddr_sweep mode=%s bytes=%lu chunks=%lu checked_words=%lu\n",
         MODE, (unsigned long)SWEEP_BYTES, (unsigned long)chunks, (unsigned long)words);
  return 0;
}
