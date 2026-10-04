// SPDX-License-Identifier: Apache-2.0
// One outstanding AXI-Lite read and write; AW and W may arrive independently.
module matrix_axi_lite #(
  parameter type req_t = logic,
  parameter type resp_t = logic
) (
  input logic clk_i, rst_ni,
  input req_t req_i, output resp_t resp_o,
  input logic cmd_valid_i, cmd_macc_i,
  output logic cmd_ready_o, done_o
);
  logic aw_q, w_q, b_q, r_q;
  logic [11:0] addr_q;
  logic [63:0] data_q, rdata_q;
  logic [7:0] strb_q;
  logic berr_q, rerr_q;
  logic reg_valid, reg_write, reg_ready, reg_error;
  logic [11:0] reg_addr;
  logic [63:0] reg_rdata;
  logic tile_ready, tile_valid, quiet;

  assign reg_write = aw_q && w_q && !b_q;
  assign reg_valid = reg_write || (req_i.ar_valid && !r_q);
  assign reg_addr = reg_write ? addr_q : req_i.ar.addr[11:0];
  assign quiet = !(aw_q || w_q || b_q || r_q || req_i.aw_valid || req_i.w_valid || req_i.ar_valid);
  assign tile_valid = cmd_valid_i && quiet;
  assign cmd_ready_o = tile_ready && quiet;
  matrix_tile i_tile (
    .clk_i, .rst_ni, .cmd_valid_i(tile_valid), .cmd_macc_i,
    .cmd_ready_o(tile_ready), .done_o, .busy_o(),
    .reg_valid_i(reg_valid), .reg_write_i(reg_write), .reg_addr_i(reg_addr),
    .reg_wdata_i(data_q), .reg_strb_i(strb_q), .reg_ready_o(reg_ready),
    .reg_error_o(reg_error), .reg_rdata_o(reg_rdata)
  );
  always_comb begin
    resp_o = '0;
    resp_o.aw_ready = !aw_q && !b_q;
    resp_o.w_ready = !w_q && !b_q;
    resp_o.b_valid = b_q;
    resp_o.b.resp = berr_q ? 2'b10 : 2'b00;
    resp_o.ar_ready = !r_q && !reg_write && reg_ready;
    resp_o.r_valid = r_q;
    resp_o.r.data = rdata_q;
    resp_o.r.resp = rerr_q ? 2'b10 : 2'b00;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      aw_q<=0; w_q<=0; b_q<=0; r_q<=0;
      addr_q<='0; data_q<='0; strb_q<='0; rdata_q<='0;
      berr_q<=0; rerr_q<=0;
    end else begin
      if (req_i.aw_valid && resp_o.aw_ready) begin aw_q<=1; addr_q<=req_i.aw.addr[11:0]; end
      if (req_i.w_valid && resp_o.w_ready) begin w_q<=1; data_q<=req_i.w.data; strb_q<=req_i.w.strb; end
      if (reg_write && reg_ready) begin aw_q<=0; w_q<=0; b_q<=1; berr_q<=reg_error; end
      if (b_q && req_i.b_ready) b_q<=0;
      if (req_i.ar_valid && resp_o.ar_ready) begin
        r_q<=1; rdata_q<=reg_rdata; rerr_q<=reg_error;
      end
      if (r_q && req_i.r_ready) r_q<=0;
    end
  end
endmodule
