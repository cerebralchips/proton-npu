// SPDX-License-Identifier: Apache-2.0
// DDR A/B -> SRAM A/B -> vector add into SRAM C -> DDR C -> scalar check.
#include <stddef.h>
#include <stdint.h>
#include <riscv_vector.h>
#include "printf.h"

#ifndef ELEMENTS
#define ELEMENTS 4099UL
#endif
#ifndef PASSES
#define PASSES 1UL
#endif
#ifndef CHUNK_WORDS
#define CHUNK_WORDS 1024UL
#endif
#ifndef INJECT_FAILURE
#define INJECT_FAILURE 0
#endif

#define GUARD UINT32_C(0xdeadbeef)
#define DDR_A ((uint32_t *)(uintptr_t)UINT64_C(0x100000000))
#define DDR_B ((uint32_t *)(uintptr_t)UINT64_C(0x140000000))
#define DDR_C ((uint32_t *)(uintptr_t)UINT64_C(0x180000000))
_Static_assert(sizeof(uintptr_t) == 8, "Requires RV64");
_Static_assert(ELEMENTS > 0 && ELEMENTS <= 1048576UL, "Use 1..1048576 elements per buffer");
_Static_assert(PASSES > 0 && PASSES <= 100000UL, "Use 1..100000 passes");
_Static_assert(CHUNK_WORDS > 0 && CHUNK_WORDS <= 16384UL, "Keep SRAM scratch buffers small");

// All three arrays live in internal SRAM, together with code and stack.
static uint32_t sram_a[CHUNK_WORDS + 1] __attribute__((aligned(64)));
static uint32_t sram_b[CHUNK_WORDS + 1] __attribute__((aligned(64)));
static uint32_t sram_c[CHUNK_WORDS + 1] __attribute__((aligned(64)));
static inline void fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static inline uint64_t cycles(void) {
  uint64_t c;
  __asm__ volatile("rdcycle %0" : "=r"(c) :: "memory");
  return c;
}

// Scalar initialization and verification are compiled with auto-vectorization off.
__attribute__((noinline)) static void initialize(uint32_t pass) {
  for (size_t i = 0; i < ELEMENTS; ++i) {
    ((volatile uint32_t *)DDR_A)[i] = (uint32_t)i + pass;
    ((volatile uint32_t *)DDR_B)[i] = 2u*(uint32_t)i + 1u;
    // Poison each output so a missing store is detected even on repeated passes.
    ((volatile uint32_t *)DDR_C)[i] = ~(3u*(uint32_t)i + pass + 1u);
  }
  ((volatile uint32_t *)DDR_A)[ELEMENTS] = GUARD;
  ((volatile uint32_t *)DDR_B)[ELEMENTS] = GUARD;
  ((volatile uint32_t *)DDR_C)[ELEMENTS] = GUARD;
  fence();
}

// A copy needs a vector LOAD into registers, then a vector STORE to the destination.
// There is no memory-to-memory instruction and no DMA engine involved here.
__attribute__((noinline)) static void vector_copy(const uint32_t *src,
                                                 uint32_t *dst, size_t n) {
  while (n) {
    size_t vl = __riscv_vsetvl_e32m1(n);
    vuint32m1_t v = __riscv_vle32_v_u32m1(src, vl);
    __riscv_vse32_v_u32m1(dst, v, vl);
    src += vl; dst += vl; n -= vl;
  }
}

__attribute__((noinline)) static void vector_add(size_t n) {
  for (size_t off = 0; off < n;) {
    size_t vl = __riscv_vsetvl_e32m1(n - off);
    vuint32m1_t a = __riscv_vle32_v_u32m1(sram_a + off, vl);
    vuint32m1_t b = __riscv_vle32_v_u32m1(sram_b + off, vl);
    vuint32m1_t c = __riscv_vadd_vv_u32m1(a, b, vl);
    __riscv_vse32_v_u32m1(sram_c + off, c, vl);
    off += vl;
  }
}

__attribute__((noinline)) static int verify(uint32_t pass) {
  // Check every result and that neither DDR input was modified.
  for (size_t i = 0; i < ELEMENTS; ++i) {
    uint32_t a = ((volatile uint32_t *)DDR_A)[i];
    uint32_t b = ((volatile uint32_t *)DDR_B)[i];
    uint32_t c = ((volatile uint32_t *)DDR_C)[i];
    uint32_t expected = 3u*(uint32_t)i + pass + 1u;
    if (a != (uint32_t)i + pass || b != 2u*(uint32_t)i + 1u || c != expected) {
      printf("RESULT: FAIL ddr_vector_add pass=%lu index=%lu A=%lu B=%lu got=%lu expected=%lu\n",
             (unsigned long)pass, (unsigned long)i, (unsigned long)a,
             (unsigned long)b, (unsigned long)c, (unsigned long)expected);
      return 1;
    }
  }
  if (((volatile uint32_t *)DDR_A)[ELEMENTS] != GUARD ||
      ((volatile uint32_t *)DDR_B)[ELEMENTS] != GUARD ||
      ((volatile uint32_t *)DDR_C)[ELEMENTS] != GUARD) {
    printf("RESULT: FAIL ddr_vector_add DDR guard changed\n");
    return 1;
  }
  return 0;
}

int main(void) {
  printf("DDR VECTOR ADD: elements=%lu passes=%lu chunk_words=%lu\n",
         (unsigned long)ELEMENTS, (unsigned long)PASSES, (unsigned long)CHUNK_WORDS);
  printf("FLOW: DDR A/B -> SRAM A/B -> vector add -> SRAM C -> DDR C -> scalar check\n");
  uint64_t init_cycles = 0, compute_cycles = 0, verify_cycles = 0;
  for (size_t pass = 0; pass < PASSES; ++pass) {
    printf("PASS %lu/%lu: initialize DDR inputs and poison output\n",
           (unsigned long)(pass + 1), (unsigned long)PASSES);
    uint64_t t0 = cycles();
    initialize((uint32_t)pass);
    uint64_t t1 = cycles();
    printf("PASS %lu/%lu: vector copies and addition through SRAM\n",
           (unsigned long)(pass + 1), (unsigned long)PASSES);
    uint64_t t2 = cycles();
    for (size_t off = 0; off < ELEMENTS;) {
      size_t n = ELEMENTS - off;
      if (n > CHUNK_WORDS) n = CHUNK_WORDS;
      sram_a[n] = GUARD; sram_b[n] = GUARD; sram_c[n] = GUARD; fence();
      vector_copy(DDR_A + off, sram_a, n);
      vector_copy(DDR_B + off, sram_b, n); fence();
      vector_add(n); fence();
      vector_copy(sram_c, DDR_C + off, n); fence();
      if (sram_a[n] != GUARD || sram_b[n] != GUARD || sram_c[n] != GUARD) {
        printf("RESULT: FAIL ddr_vector_add SRAM guard changed\n");
        return 2;
      }
      off += n;
    }
    uint64_t t3 = cycles();
    if (INJECT_FAILURE) { ((volatile uint32_t *)DDR_C)[ELEMENTS - 1] ^= 1u; fence(); }
    printf("PASS %lu/%lu: compare every DDR result with scalar reference\n",
           (unsigned long)(pass + 1), (unsigned long)PASSES);
    uint64_t t4 = cycles();
    if (verify((uint32_t)pass)) return 1;
    uint64_t t5 = cycles();
    init_cycles += t1 - t0; compute_cycles += t3 - t2; verify_cycles += t5 - t4;
    printf("CHECK %lu/%lu OK: %lu results match; inputs and guards intact\n",
           (unsigned long)(pass + 1), (unsigned long)PASSES, (unsigned long)ELEMENTS);
  }
  printf("ADD_CYCLES init=%lu copies_and_add=%lu verify=%lu\n",
         (unsigned long)init_cycles, (unsigned long)compute_cycles, (unsigned long)verify_cycles);
  printf("RESULT: PASS ddr_vector_add elements=%lu passes=%lu checked_outputs=%lu\n",
         (unsigned long)ELEMENTS, (unsigned long)PASSES, (unsigned long)(ELEMENTS*PASSES));
  return 0;
}
