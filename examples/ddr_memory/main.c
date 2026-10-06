// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stddef.h>
#include <riscv_vector.h>
#include "printf.h"

#define DDR_BASE UINT64_C(0x100000000)
#define DDR_BYTES UINT64_C(0x100000000)
#define SAMPLE_COUNT 4096U
extern uint64_t ddr_probe_load(uintptr_t address);
static uint64_t sram_guard[32] __attribute__((aligned(64)));
static uint32_t vector_input[67] __attribute__((aligned(64)));
static uint32_t vector_output[67] __attribute__((aligned(64)));
static inline void fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static inline void put(uint64_t address, uint64_t value) {
  *(volatile uint64_t *)(uintptr_t)address = value;
}
static inline uint64_t get(uint64_t address) {
  return *(volatile uint64_t *)(uintptr_t)address;
}
static uint64_t pattern(uint64_t address) {
  return (address * UINT64_C(0x9e3779b97f4a7c15)) ^ (address >> 32) ^ UINT64_C(0xd3c5a709abcd1234);
}
static int check(uint64_t address, uint64_t expected) {
  uint64_t actual = get(address);
  if (actual == expected) return 0;
  printf("FAIL address=%lx expected=%lx actual=%lx\n", (unsigned long)address,
         (unsigned long)expected, (unsigned long)actual);
  return 1;
}
int main(void) {
  printf("Proton DDR: SRAM=16MiB DDR=4GiB base=100000000 end=200000000\n");
  if (get(0xd0000008) != 0x80000000 || get(0xd0000010) != 0x81000000) return 1;
  if(check(DDR_BASE+0x8000,UINT64_C(0x0123456789abcdef)) ||
     check(DDR_BASE+DDR_BYTES-8,UINT64_C(0xfedcba9876543210))) return 14;
  printf("PASS ELF preload above 4GiB and at final DDR word\n");
  for (unsigned i=0; i<32; ++i) sram_guard[i] = pattern((uintptr_t)(sram_guard+i));
  // Exercise the same low 32 address bits in each region; they must not alias.
  for (unsigned i=0; i<32; ++i) put(DDR_BASE+(uintptr_t)(sram_guard+i), ~sram_guard[i]);
  fence();
  for (unsigned i=0; i<32; ++i)
    if (sram_guard[i] != pattern((uintptr_t)(sram_guard+i)) ||
        check(DDR_BASE+(uintptr_t)(sram_guard+i), ~sram_guard[i])) return 2;
  // All word-address bits, including the upper half of the 4 GiB region.
  put(DDR_BASE, pattern(DDR_BASE));
  for (unsigned bit=3; bit<32; ++bit) {
    uint64_t a=DDR_BASE+(UINT64_C(1)<<bit); put(a,pattern(a));
  }
  put(DDR_BASE+DDR_BYTES-8,pattern(DDR_BASE+DDR_BYTES-8)); fence();
  if (check(DDR_BASE,pattern(DDR_BASE)) ||
      check(DDR_BASE+DDR_BYTES-8,pattern(DDR_BASE+DDR_BYTES-8))) return 3;
  for (unsigned bit=3; bit<32; ++bit) {
    uint64_t a=DDR_BASE+(UINT64_C(1)<<bit); if(check(a,pattern(a))) return 4;
  }
  printf("PASS SRAM isolation and DDR address bits 3..31\n");
  // One word in every MiB across the entire 4 GiB address space, two patterns.
  // Write the whole sample set before reading, so address aliasing is observable.
  for (unsigned pass=0; pass<2; ++pass) {
    for (unsigned i=0; i<SAMPLE_COUNT; ++i) {
      uint64_t a=DDR_BASE+((uint64_t)i<<20)+0x1000;
      put(a,pass ? ~pattern(a) : pattern(a));
    }
    fence();
    for (unsigned i=SAMPLE_COUNT; i-->0;) {
      uint64_t a=DDR_BASE+((uint64_t)i<<20)+0x1000;
      if(check(a,pass ? ~pattern(a) : pattern(a))) return 5;
    }
  }
  printf("PASS 4096 locations across 4GiB, two complementary patterns\n");
  // Walking ones/zeros checks the full data bus independently of address pattern.
  for(unsigned bit=0;bit<64;++bit) {
    uint64_t p=UINT64_C(1)<<bit;
    put(DDR_BASE,p); fence(); if(check(DDR_BASE,p)) return 6;
    put(DDR_BASE,~p); fence(); if(check(DDR_BASE,~p)) return 7;
  }
  // Byte enables on the final word: touch the actual last byte of the region.
  uint64_t last=DDR_BASE+DDR_BYTES-8, expected=0;
  put(last,0); fence();
  for(unsigned byte=0;byte<8;++byte) {
    uint8_t value=(uint8_t)(0xa0+byte);
    *(volatile uint8_t *)(uintptr_t)(last+byte)=value;
    expected |= (uint64_t)value<<(byte*8); fence();
    if(check(last,expected)) return 8;
  }
  *(volatile uint16_t *)(uintptr_t)(last+2)=0xbeef;
  expected=(expected & ~UINT64_C(0xffff0000))|UINT64_C(0xbeef0000); fence();
  if(check(last,expected)) return 9;
  *(volatile uint32_t *)(uintptr_t)(last+4)=0x12345678;
  expected=(expected & UINT64_C(0xffffffff))|UINT64_C(0x1234567800000000); fence();
  if(check(last,expected)) return 10;
  printf("PASS walking data bits and byte/halfword/word strobes at DDR end\n");
  // RVV bursts and a tail, followed by scalar verification through the CPU.
  for(unsigned i=0;i<67;++i) vector_input[i]=0x12340000+i*37;
  uint32_t *external=(uint32_t *)(uintptr_t)(DDR_BASE+0x1234000);
  for(size_t off=0;off<67;) {
    size_t vl=__riscv_vsetvl_e32m1(67-off);
    vuint32m1_t v=__riscv_vle32_v_u32m1(vector_input+off,vl);
    __riscv_vse32_v_u32m1(external+off,v,vl); off+=vl;
  }
  fence();
  for(size_t off=0;off<67;) {
    size_t vl=__riscv_vsetvl_e32m1(67-off);
    vuint32m1_t v=__riscv_vle32_v_u32m1(external+off,vl);
    __riscv_vse32_v_u32m1(vector_output+off,v,vl); off+=vl;
  }
  fence();
  for(unsigned i=0;i<67;++i)
    if(vector_output[i]!=vector_input[i] || ((volatile uint32_t *)external)[i]!=vector_input[i]) return 11;
  printf("PASS RVV DDR bursts and 67-element tail\n");
  // This pinned CVA6 cache adapter does not propagate AXI errors as CPU traps.
  // The independent FST checker requires DECERR for each read and write below.
  fence();
  ddr_probe_load(0x81000000); // first byte beyond installed SRAM
  ddr_probe_load(DDR_BASE-8);
  ddr_probe_load(DDR_BASE+DDR_BYTES);
  put(0x81000000,0xdeadbeef);
  put(DDR_BASE-8,0xdeadbeef);
  put(DDR_BASE+DDR_BYTES,0xdeadbeef); fence();
  if(check(last,expected)) return 12;
  for(unsigned i=0;i<32;++i)
    if(sram_guard[i]!=pattern((uintptr_t)(sram_guard+i))) return 13;
  printf("BOUNDARY: three unmapped reads/writes issued; verify AXI DECERR in trace\n");
  printf("RESULT: PASS ddr_memory sampled=4096 bytes=4294967296\n");
  return 0;
}
