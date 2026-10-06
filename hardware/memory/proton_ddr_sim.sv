// SPDX-License-Identifier: Apache-2.0
// Functional AXI-backed external memory. Not a DDR PHY or timing model.
module proton_ddr_sim #(
  parameter type req_t = logic,
  parameter type resp_t = logic,
  parameter int unsigned IdWidth = 5,
  parameter logic [63:0] Base = 64'h1_0000_0000,
  parameter logic [63:0] Bytes = 64'h1_0000_0000
)(input logic clk_i, rst_ni, input req_t req_i, output resp_t resp_o);
  req_t filtered_req;
  resp_t filtered_resp;
  axi_atop_filter #(.AxiIdWidth(IdWidth), .AxiMaxWriteTxns(4),
    .axi_req_t(req_t), .axi_resp_t(resp_t)) i_atop_filter (
    .clk_i, .rst_ni, .slv_req_i(req_i), .slv_resp_o(resp_o),
    .mst_req_o(filtered_req), .mst_resp_i(filtered_resp));

  logic mem_req, mem_gnt, mem_we, mem_rvalid, mem_error;
  logic [63:0] mem_addr, mem_wdata, mem_rdata;
  logic [7:0] mem_strb;
  axi_to_detailed_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(IdWidth),
    .UserWidth(1), .NumBanks(1), .BufDepth(1),
    .axi_req_t(req_t), .axi_resp_t(resp_t)) i_bridge (
    .clk_i, .rst_ni, .axi_req_i(filtered_req), .axi_resp_o(filtered_resp),
    .mem_req_o(mem_req), .mem_gnt_i(mem_gnt), .mem_we_o(mem_we),
    .mem_addr_o(mem_addr), .mem_strb_o(mem_strb), .mem_wdata_o(mem_wdata),
    .mem_rdata_i(mem_rdata), .mem_rvalid_i(mem_rvalid), .mem_err_i(mem_error),
    .mem_exokay_i(1'b0), .mem_atop_o(), .mem_lock_o(), .mem_id_o(),
    .mem_user_o(), .mem_cache_o(), .mem_prot_o(), .mem_qos_o(),
    .mem_region_o(), .busy_o());

  // Allocate only touched words: exposing 4 GiB does not allocate 4 GiB on the host.
  // Unwritten locations read as zero. Reset clears protocol state, not contents.
  bit [63:0] words [longint unsigned];
  int unsigned latency = 3, stall_cycles = 0, remaining, cooldown;
  logic pending;
  logic [63:0] pending_data;
  logic pending_error;
  longint unsigned reads, writes;
  initial begin
    void'($value$plusargs("ddr_latency=%d", latency));
    void'($value$plusargs("ddr_stall=%d", stall_cycles));
    if (latency < 1 || latency > 1024 || stall_cycles > 1024)
      $fatal(1, "DDR latency must be 1..1024; stall must be 0..1024");
    $display("DDR_CONFIG base=%h bytes=%h latency=%0d stall=%0d", Base, Bytes,
             latency, stall_cycles);
  end
  assign mem_gnt = rst_ni && !pending && cooldown == 0;
  always_ff @(posedge clk_i or negedge rst_ni) begin : memory_cycle
    longint unsigned index;
    bit [63:0] value;
    if (!rst_ni) begin
      pending <= 0; remaining <= 0; cooldown <= 0;
      mem_rvalid <= 0; mem_rdata <= 0; mem_error <= 0;
      pending_data <= 0; pending_error <= 0; reads <= 0; writes <= 0;
    end else begin
      mem_rvalid <= 0;
      if (cooldown != 0) cooldown <= cooldown - 1;
      if (pending) begin
        if (remaining == 1) begin
          mem_rvalid <= 1; mem_rdata <= pending_data; mem_error <= pending_error;
          pending <= 0; cooldown <= stall_cycles;
        end else remaining <= remaining - 1;
      end
      if (mem_req && mem_gnt) begin
        pending <= 1; remaining <= latency;
        pending_error <= mem_addr < Base || mem_addr >= Base + Bytes;
        pending_data <= 0;
        if (mem_addr >= Base && mem_addr < Base + Bytes) begin
          index = (mem_addr - Base) >> 3;
          value = words.exists(index) ? words[index] : 64'b0;
          if (mem_we) begin
            for (int b = 0; b < 8; b++)
              if (mem_strb[b]) value[8*b +: 8] = mem_wdata[8*b +: 8];
            words[index] = value;
            writes <= writes + 1;
          end else begin
            pending_data <= value; reads <= reads + 1;
          end
        end
      end
    end
  end
  final $display("DDR_ACCESSES reads=%0d writes=%0d allocated_words=%0d",
                 reads, writes, words.num());

  // Same DPI loader contract as tc_sram. Word indices fit in signed int for 4 GiB.
  export "DPI-C" function simutil_set_mem;
  function int simutil_set_mem(input int index, input bit [511:0] val);
    if (index < 0 || 64'(index) >= (Bytes >> 3)) return 0;
    words[64'(index)] = val[63:0];
    return 1;
  endfunction
  export "DPI-C" function simutil_memload;
  function void simutil_memload(input string file);
    $fatal(1, "DDR requires address-aware ELF loading (-E), not VMEM");
  endfunction
endmodule
