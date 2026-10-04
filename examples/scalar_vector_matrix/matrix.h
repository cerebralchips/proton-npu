// SPDX-License-Identifier: Apache-2.0
#ifndef MATRIX_V1_H
#define MATRIX_V1_H
#include <stdint.h>
#include <stddef.h>
#define MATRIX_BASE ((uintptr_t)0xe0000000UL)
static inline volatile uint32_t *matrix_reg(size_t offset) {
  return (volatile uint32_t *)(MATRIX_BASE + offset);
}
static inline void matrix_fence(void) { __asm__ volatile("fence iorw, iorw" ::: "memory"); }
static inline uintptr_t matrix_zero(void) {
  uintptr_t status;
  __asm__ volatile(".insn r 0x2b, 0, 0, %0, x0, x0" : "=r"(status) :: "memory");
  return status;
}
static inline uintptr_t matrix_macc(void) {
  uintptr_t status;
  __asm__ volatile(".insn r 0x2b, 0, 1, %0, x0, x0" : "=r"(status) :: "memory");
  return status;
}
// Exclusive single-hart ownership; conventional row-major A[M][K], B[K][N], C[M][N].
// INT32 results are represented by uint32_t to make wraparound explicit in C.
int matrix_multiply(const int8_t *a, const int8_t *b, uint32_t *c,
                    size_t m, size_t n, size_t k);
#endif
