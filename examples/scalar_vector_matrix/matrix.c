// SPDX-License-Identifier: Apache-2.0
#include "matrix.h"
int matrix_multiply(const int8_t *a, const int8_t *b, uint32_t *c,
                    size_t m, size_t n, size_t k) {
  matrix_fence();
  for (size_t i=0;i<m;i+=4) for (size_t j=0;j<n;j+=4) {
    if (matrix_zero()) return 1;
    for (size_t p=0;p<k;p+=16) {
      for (size_t r=0;r<4;r++) for (size_t group=0;group<4;group++) {
        uint32_t aw=0,bw=0;
        for (size_t lane=0;lane<4;lane++) {
          size_t q=p+group*4+lane;
          if (i+r<m && q<k) aw|=(uint32_t)(uint8_t)a[(i+r)*k+q]<<(8*lane);
          if (j+r<n && q<k) bw|=(uint32_t)(uint8_t)b[q*n+j+r]<<(8*lane);
        }
        *matrix_reg(0x100+(r*4+group)*4)=aw;
        *matrix_reg(0x140+(r*4+group)*4)=bw;
      }
      matrix_fence();
      if (matrix_macc()) return 2;
    }
    matrix_fence();
    for (size_t r=0;r<4 && i+r<m;r++) for (size_t col=0;col<4 && j+col<n;col++)
      c[(i+r)*n+j+col]=*matrix_reg(0x180+(r*4+col)*4);
  }
  matrix_fence();
  return 0;
}
