// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#define DMA UINT64_C(0xe0001000)
#define SRAM UINT64_C(0x80800000)
#define DDR UINT64_C(0x100000000)
static inline void fence(void) { __asm__ volatile("fence iorw,iorw" ::: "memory"); }
static void put(unsigned off,uint64_t v) { *(volatile uint64_t *)(uintptr_t)(DMA+off)=v; }
static uint64_t get(unsigned off) { return *(volatile uint64_t *)(uintptr_t)(DMA+off); }
static uint8_t load(uint64_t p) { return *(volatile uint8_t *)(uintptr_t)p; }
static void store(uint64_t p,uint8_t v) { *(volatile uint8_t *)(uintptr_t)p=v; }
static unsigned cases=0;
static int launch(uint64_t src,uint64_t dst,unsigned rows,unsigned cols,
                  unsigned size,unsigned ss,unsigned ds,unsigned transpose,unsigned error) {
  put(0x10,src);put(0x18,dst);put(0x20,((uint64_t)cols<<16)|rows);
  put(0x28,((uint64_t)ds<<32)|ss);fence();put(0x30,1|(transpose<<1)|(size<<2));fence();
  uint64_t status=0;
  for(unsigned polls=0;polls<100000;polls++) {
    status=get(8);if(!(status&1) && (status&2)) break;
  }
  fence();
  if(status!=(error ? UINT64_C(0x106) : 2) || get(0x38)!=(error ? 0 : (uint64_t)rows*cols*(1u<<size))) {
    printf("RESULT: FAIL DMA status=%lx bytes=%lu\n",(unsigned long)status,(unsigned long)get(0x38));return 1;
  }
  return 0;
}
static int test(unsigned size,unsigned tr,unsigned reverse,unsigned rows,unsigned cols,unsigned high) {
  unsigned e=1u<<size,ss=(cols+2)*e,ds=((tr?rows:cols)+3)*e;
  uint64_t external=high ? UINT64_C(0x1fffffe00) : DDR;
  uint64_t sb=reverse?external:SRAM, db=reverse?SRAM+0x1000:external+0x100;
  // Offset within bus words; preserve all surrounding bytes and row padding.
  unsigned so=16+e*(cases%(8/e)),dof=24+e*((cases+1)%(8/e)),seed=cases+7;
  for(unsigned i=0;i<256;i++) { store(sb+i,(uint8_t)((i-so)*17+seed));store(db+i,0xcd); }
  fence();
  printf("DMA_CASE id=%u src=%lx dst=%lx rows=%u cols=%u size=%u ss=%u ds=%u transpose=%u seed=%u\n",
         cases,(unsigned long)(sb+so),(unsigned long)(db+dof),rows,cols,size,ss,ds,tr,seed);
  if(launch(sb+so,db+dof,rows,cols,size,ss,ds,tr,0)) return 1;
  uint8_t expected[256];
  for(unsigned i=0;i<256;i++) expected[i]=0xcd;
  for(unsigned r=0;r<rows;r++) for(unsigned c=0;c<cols;c++) for(unsigned b=0;b<e;b++)
    expected[dof+(tr ? c*ds+r*e+b : r*ds+c*e+b)]=(uint8_t)((r*ss+c*e+b)*17+seed);
  for(unsigned i=0;i<256;i++) {
    if(load(db+i)!=expected[i] || load(sb+i)!=(uint8_t)((i-so)*17+seed)) {
      printf("RESULT: FAIL case=%u byte=%u actual=%u expected=%u\n",cases,i,load(db+i),expected[i]);return 1;
    }
  }
  printf("DMA_CASE PASS id=%u bytes=%u\n",cases,rows*cols*e);cases++;return 0;
}
int main(void) {
  uint64_t dc;
  __asm__ volatile("csrr %0,0x7c1":"=r"(dc));
  if(dc || get(0)!=UINT64_C(0x00010000444d4131)) return 1;
  printf("DMA coherence policy: CPU data cache disabled; fenced buffer ownership\n");
  for(unsigned size=0;size<4;size++) for(unsigned tr=0;tr<2;tr++) for(unsigned dir=0;dir<2;dir++)
    if(test(size,tr,dir,3,5,(size+tr+dir)&1)) return 2;
  if(test(0,1,0,1,7,1) || test(1,1,1,7,1,1) || test(3,1,0,1,1,0)) return 3;
  // The final DDR byte is reached in each direction, with an independent byte pattern.
  for(unsigned i=0;i<8;i++) store(SRAM+i,(uint8_t)(17*i+91));
  printf("DMA_CASE id=%u src=%lx dst=1fffffff8 rows=1 cols=1 size=3 ss=8 ds=8 transpose=0 seed=91\n",cases,(unsigned long)SRAM);
  if(launch(SRAM,UINT64_C(0x1fffffff8),1,1,3,8,8,0,0)) return 4;
  cases++;
  printf("DMA_CASE id=%u src=1fffffff8 dst=%lx rows=1 cols=1 size=3 ss=8 ds=8 transpose=0 seed=91\n",cases,(unsigned long)(SRAM+0x1000));
  if(launch(UINT64_C(0x1fffffff8),SRAM+0x1000,1,1,3,8,8,0,0)) return 5;
  for(unsigned i=0;i<8;i++) if(load(SRAM+0x1000+i)!=(uint8_t)(17*i+91)) return 6;
  cases++;
  if(launch(SRAM,DDR,0,1,0,1,1,0,1) ||
     launch(SRAM+1,DDR,1,1,3,8,8,0,1) ||
     launch(SRAM,DDR,2,5,0,4,5,0,1) ||
     launch(SRAM,UINT64_C(0x1fffffff8),1,2,3,16,16,0,1) ||
     launch(UINT64_C(0x80fffff8),DDR,1,2,3,16,16,0,1) ||
     launch(UINT64_C(0xfffffffffffffff8),SRAM,1,2,3,16,16,0,1)) return 7;
  put(0x30,16);if(get(8)!=0 || get(0x38)!=0) return 8;
  printf("RESULT: PASS dma_transfer cases=%u invalid_descriptors=6 copy_transpose_guards=PASS\n",cases);
  return 0;
}
