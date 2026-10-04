// SPDX-License-Identifier: Apache-2.0
// One bare-metal program: scalar setup -> RVV computation -> scalar checking.
#include <stddef.h>
#include <stdint.h>
#include <riscv_vector.h>
#ifdef SPIKE
#include <stdio.h>
#else
#include "printf.h"
#endif

#define CAPACITY 257
#define GUARD UINT32_C(0xcafe0123)
#ifndef INJECT_FAILURE
#define INJECT_FAILURE 0
#endif

static uint32_t a[CAPACITY] __attribute__((aligned(64)));
static uint32_t b[CAPACITY] __attribute__((aligned(64)));
static uint32_t out[CAPACITY + 1] __attribute__((aligned(64)));

// Useful symbols when matching the ELF disassembly to the waveform.
__attribute__((noinline))
static void vector_add(const uint32_t *lhs, const uint32_t *rhs,
                       uint32_t *dst, size_t n) {
  while (n) {
    size_t vl = __riscv_vsetvl_e32m1(n);
    vuint32m1_t x = __riscv_vle32_v_u32m1(lhs, vl);
    vuint32m1_t y = __riscv_vle32_v_u32m1(rhs, vl);
    vuint32m1_t z = __riscv_vadd_vv_u32m1(x, y, vl);
    __riscv_vse32_v_u32m1(dst, z, vl);
    lhs += vl;
    rhs += vl;
    dst += vl;
    n -= vl;
  }
}

__attribute__((noinline))
static uint32_t vector_sum(const uint32_t *src, size_t n) {
  uint32_t sum = 0;
  while (n) {
    size_t vl = __riscv_vsetvl_e32m1(n);
    vuint32m1_t values = __riscv_vle32_v_u32m1(src, vl);
    vuint32m1_t seed = __riscv_vmv_v_x_u32m1(sum, 1);
    vuint32m1_t reduced = __riscv_vredsum_vs_u32m1_u32m1(values, seed, vl);
    sum = __riscv_vmv_x_s_u32m1_u32(reduced);
    src += vl;
    n -= vl;
  }
  return sum;
}

int main(void) {
  // Scalar code in this example is compiled with auto-vectorization disabled.
  const size_t lengths[] = {0, 1, 7, 63, 64, 65, 127, 128, 129, CAPACITY};
  size_t vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
  printf("CVA6 + Ara scalar/vector C demo: VLEN=%lu bits\n",
         (unsigned long)(vlenb * 8));
  if (vlenb != 256) {
    printf("FAIL: this lesson expects the two-lane VLEN=2048 configuration\n");
    return 1;
  }
  for (size_t i = 0; i < CAPACITY; ++i) {
    a[i] = (uint32_t)i;
    b[i] = 2u * (uint32_t)i + 1u;
  }
  for (size_t k = 0; k < sizeof(lengths) / sizeof(lengths[0]); ++k) {
    size_t n = lengths[k];
    for (size_t i = 0; i <= CAPACITY; ++i) out[i] = GUARD;
    vector_add(a, b, out, n);
    uint32_t expected_sum = 0;
    for (size_t i = 0; i < n; ++i) {
      uint32_t expected = a[i] + b[i];
      if (out[i] != expected) {
        printf("FAIL: n=%lu index=%lu got=%lu expected=%lu\n",
               (unsigned long)n, (unsigned long)i,
               (unsigned long)out[i], (unsigned long)expected);
        return 2;
      }
      expected_sum += expected;
    }
    for (size_t i = n; i <= CAPACITY; ++i) {
      if (out[i] != GUARD) {
        printf("FAIL: vector store changed an element beyond n=%lu\n",
               (unsigned long)n);
        return 3;
      }
    }
    uint32_t sum = vector_sum(out, n);
    if (sum != expected_sum + (INJECT_FAILURE && n == CAPACITY)) {
      printf("FAIL: reduction n=%lu got=%lu expected=%lu\n",
             (unsigned long)n, (unsigned long)sum,
             (unsigned long)(expected_sum + (INJECT_FAILURE && n == CAPACITY)));
      return 4;
    }
    printf("CASE n=%lu sum=%lu PASS\n", (unsigned long)n, (unsigned long)sum);
  }
  printf("RESULT: PASS scalar_vector cases=10\n");
  return 0;
}
