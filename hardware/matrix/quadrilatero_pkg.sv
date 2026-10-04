// Minimal type adapter for the unmodified Quadrilatero integer PE/mesh.
// Values and field order match upstream quadrilatero_pkg.sv at the pinned revision.
// Copyright 2024 EPFL. SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
package quadrilatero_pkg;
  typedef enum logic [2:0] { SIZE_32 = 1, SIZE_16 = 2, SIZE_8 = 4 } datatype_t;
  typedef struct packed { logic is_float; datatype_t datatype; } sa_ctrl_t;
endpackage
