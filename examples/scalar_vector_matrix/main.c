// SPDX-License-Identifier: Apache-2.0
#include <riscv_vector.h>
#include "printf.h"
#include "matrix.h"
#include "workload.h"
#ifndef INJECT_FAILURE
#define INJECT_FAILURE 0
#endif
volatile uint32_t trap_count,trap_error;
extern void matrix_test_trap(void);
static int8_t a[9*33] __attribute__((aligned(64)));
static uint32_t out[9*8+1] __attribute__((aligned(64)));

__attribute__((noinline)) static void vector_prepare(const int8_t *src,int8_t *dst,size_t n) {
  while(n) {
    size_t vl=__riscv_vsetvl_e8m1(n);
    vint8m1_t x=__riscv_vle8_v_i8m1(src,vl);
    x=__riscv_vadd_vx_i8m1(x,1,vl);
    __riscv_vse8_v_i8m1(dst,x,vl);
    src+=vl; dst+=vl; n-=vl;
  }
}
__attribute__((noinline)) static void vector_finish(uint32_t *dst,size_t n) {
  while(n) {
    size_t vl=__riscv_vsetvl_e32m1(n);
    vuint32m1_t x=__riscv_vle32_v_u32m1(dst,vl);
    x=__riscv_vadd_vx_u32m1(x,3,vl);
    __riscv_vse32_v_u32m1(dst,x,vl);
    dst+=vl; n-=vl;
  }
}
static int instruction_checks(void) {
  uintptr_t saved,status,handler=(uintptr_t)&matrix_test_trap;
  __asm__ volatile("csrr %0, mstatus" : "=r"(saved));
  uintptr_t vs_mask=3UL<<9;
  __asm__ volatile("csrc mstatus, %0" :: "r"(vs_mask) : "memory");
  if(matrix_zero()) return 1;
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  if(status&vs_mask) return 2;
  __asm__ volatile("csrw mstatus, %0" :: "r"(saved) : "memory");
  __asm__ volatile("csrrw %0, mtvec, %1" : "=r"(saved) : "r"(handler) : "memory");
  // Reserved funct7 and nonzero rs1 must trap, without touching matrix state.
  __asm__ volatile(".word 0x0400052b\n.word 0x0000852b" ::: "memory");
  __asm__ volatile("csrw mtvec, %0" :: "r"(saved) : "memory");
  if(trap_count!=2 || trap_error) {printf("trap_count=%u trap_error=%u\n",trap_count,trap_error); return 3;}
  uint32_t before=*matrix_reg(0x14);
  // Always-taken branch over a valid mmacc: no wrong-path side effects.
  __asm__ volatile("li t0, 1\n bnez t0, 1f\n .insn r 0x2b,0,1,x0,x0,x0\n1:" ::: "t0","memory");
  if(*matrix_reg(0x14)!=before) return 4;
  // Deliberately omit software fences and use rd=x0. Hardware must order both
  // the preceding store and the immediately following independent load.
  for(int i=0;i<32;i++) {
    uint32_t value;
    __asm__ volatile("sw %2,0(%1)\n.insn r 0x2b,0,0,x0,x0,x0\nlw %0,0(%1)"
      : "=&r"(value) : "r"(matrix_reg(0x180)),"r"(123+i) : "memory");
    if(value) return 5;
  }
  printf("GUARD PASS: VS-off, illegal encodings, wrong-path, unfenced ordering\n");
  return 0;
}
int main(void) {
  printf("CVA6 + Ara + matrix: scalar/RVV/custom matrix in one ELF\n");
  if(*matrix_reg(0)!=0x4d415431u || *matrix_reg(4)!=0x00010410u) return 1;
  int guard=instruction_checks();
  if(guard) {printf("RESULT: FAIL instruction guard=%d\n",guard);return 2;}
  for(size_t t=0;t<sizeof(cases)/sizeof(cases[0]);t++) {
    const struct workload *w=&cases[t];
    size_t count=w->m*w->n;
    for(size_t i=0;i<=count;i++) out[i]=0xcafef00du;
    vector_prepare(w->raw,a,w->m*w->k);
    matrix_fence();
    uint32_t z=*matrix_reg(0x10), mm=*matrix_reg(0x14);
    if(matrix_multiply(a,w->b,out,w->m,w->n,w->k)) return 3;
    size_t tiles=((w->m+3)/4)*((w->n+3)/4);
    if(*matrix_reg(0x10)-z!=tiles || *matrix_reg(0x14)-mm!=tiles*((w->k+15)/16)) {printf("counter mismatch case=%lu zero=%u/%lu macc=%u/%lu\n",t,*matrix_reg(0x10)-z,tiles,*matrix_reg(0x14)-mm,tiles*((w->k+15)/16));return 4;}
    vector_finish(out,count);
    matrix_fence();
    if(INJECT_FAILURE && t==0) out[0]^=1;
    uint32_t checksum=0;
    for(size_t i=0;i<w->m;i++) for(size_t j=0;j<w->n;j++) {
      uint32_t reference=3;
      for(size_t k=0;k<w->k;k++) reference+=(uint32_t)((int32_t)a[i*w->k+k]*(int32_t)w->b[k*w->n+j]);
      size_t index=i*w->n+j;
      if(out[index]!=reference || out[index]!=w->expected[index]) {
        printf("RESULT: FAIL case=%lu element=%lu got=%u scalar=%u oracle=%u\n",
          t,index,out[index],reference,w->expected[index]); return 5;
      }
      checksum+=out[index];
    }
    if(out[count]!=0xcafef00du) return 6;
    printf("CASE %lu M=%lu N=%lu K=%lu checksum=%u PASS\n",t,w->m,w->n,w->k,checksum);
  }
  printf("RESULT: PASS scalar_vector_matrix cases=8\n");
  return 0;
}
