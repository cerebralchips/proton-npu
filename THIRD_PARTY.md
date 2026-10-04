# Third-party code and attribution

The root [Apache-2.0 license](LICENSE) applies to Cerebral Chips' original work.
Existing file notices, third-party licenses and dependency terms remain applicable.
This repository is an integration layer, not a claim of authorship over the IP below.

| Component | Pinned source | License / treatment |
| --- | --- | --- |
| Ara | [PULP, 34bd3bc](https://github.com/pulp-platform/ara/tree/34bd3bc152421b4601a7bf3d6e8e91ffb545c99e) | Main hardware license Solderpad 0.51; software commonly Apache-2.0; preserve per-file exceptions |
| CVA6 | [PULP, 99eac9a](https://github.com/pulp-platform/cva6/tree/99eac9a649001bdf5b8f9da52e0ca73d5c48db1c) | Main hardware license Solderpad 0.51; also includes BSD and Apache notices |
| Quadrilatero | [PULP/EPFL, 4e4f415](https://github.com/pulp-platform/quadrilatero/tree/4e4f41520d0784ecb750a22d0715d5a22cca8e26) | Vendored integer MAC, PE and mesh: Apache-2.0 WITH SHL-2.1 |
| LLVM | 20.1.0 | Apache-2.0 WITH LLVM-exception; downloaded, not vendored |
| Verilator | Ara-pinned revision | LGPL-3.0 or Artistic-2.0; fetched/build tool |
| Spike | Ara-pinned revision | BSD-style upstream notices; fetched simulator |
| GCC / Binutils / Newlib | Matched CVA6 runtime recipe | GPL tool licenses, GCC runtime exception and Newlib's per-file licenses; preserve upstream notices |
| Lima / Bender | Checksummed versions in source lock | Apache-2.0 tools; downloaded, not vendored |

Vendored Quadrilatero files and their SHA-256 digests are listed in
[provenance.json](hardware/matrix/vendor/quadrilatero/provenance.json). Their
[license](hardware/matrix/vendor/quadrilatero/LICENSE.md) and original headers are
kept intact. The small [package adapter](hardware/matrix/quadrilatero_pkg.sv)
derives upstream types and retains Apache-2.0 WITH SHL-2.1.

Ara and CVA6 are fetched into ignored `upstream/`; their own dependency graph and
license files accompany that checkout. Reviewable patches under `patches/` modify
those sources and do not replace their existing licenses. Copies of the main
hardware license texts are in [licenses/](licenses/). This is an inventory of the
selected major components, not a claim that every transitive source has one license.

Original Cerebral Chips contributions include the matrix control/bus/router
integration, C library, independent verification, workflow scripts and documentation,
except where the files explicitly retain upstream authorship or license notices.
