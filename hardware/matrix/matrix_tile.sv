// SPDX-License-Identifier: Apache-2.0
// Fixed 4x4 output tile: C += signed A[4][16] * signed BT[4][16]^T.
// Local register interface has a 64-bit little-endian data bus and byte enables.
module matrix_tile (
  input logic clk_i, rst_ni,
  input logic cmd_valid_i, cmd_macc_i,
  output logic cmd_ready_o, done_o, busy_o,
  input logic reg_valid_i, reg_write_i,
  input logic [11:0] reg_addr_i,
  input logic [63:0] reg_wdata_i,
  input logic [7:0] reg_strb_i,
  output logic reg_ready_o, reg_error_o,
  output logic [63:0] reg_rdata_o
);
  logic [15:0][31:0] a_q, bt_q, c_q;
  logic active_q;
  logic [3:0] step_q;
  logic [31:0] zero_count_q, macc_count_q;
  logic pump;
  logic [3:0][31:0] left_data, top_acc, bottom_acc;
  logic [3:0][3:0][31:0] weights;
  quadrilatero_pkg::sa_ctrl_t [3:0] controls;
  logic buffer_address;
  integer word_index;

  assign busy_o = active_q;
  assign reg_ready_o = !active_q;
  // Register transfers win arbitration; the CPU drains its stores before issuing.
  assign cmd_ready_o = !active_q && !reg_valid_i;
  assign pump = active_q && step_q < 10;

  always_comb begin
    left_data = '0;
    top_acc = '0;
    weights = '0;
    for (int r=0; r<4; r++) begin
      controls[r] = '{is_float: 1'b0, datatype: quadrilatero_pkg::SIZE_8};
      // Advance n injects A row (n-r), K group r, into mesh row r.
      if (int'(step_q) >= r && int'(step_q) < r+4)
        left_data[r] = a_q[(int'(step_q)-r)*4+r];
      if (int'(step_q) >= r && int'(step_q) < r+4)
        top_acc[r] = c_q[(int'(step_q)-r)*4+r];
      for (int col=0; col<4; col++) weights[r][col] = bt_q[col*4+r];
    end
  end

  quadrilatero_mesh #(.MESH_WIDTH(4), .DATA_WIDTH(32), .ENABLE_SIMD(1), .FPU(0)) i_mesh (
    .clk_i, .rst_ni, .pump_i(pump), .sa_ctrl_i(controls),
    .data_i(left_data), .acc_i(top_acc), .weight_i(weights), .acc_o(bottom_acc)
  );

  // Every aligned 64-bit beat selects two adjacent 32-bit words. Low address
  // bits select byte lanes at the bus initiator, as required by AXI narrow accesses.
  always_comb begin
    word_index = int'({reg_addr_i[5:3], 1'b0});
    buffer_address = reg_addr_i >= 12'h100 && reg_addr_i < 12'h1c0;
    reg_rdata_o = '0;
    reg_error_o = 1'b0;
    case (reg_addr_i[11:3])
      9'h000: reg_rdata_o = 64'h0001_0410_4d41_5431; // version, shape, MAT1
      9'h001: reg_rdata_o = {63'b0, active_q};
      9'h002: reg_rdata_o = {macc_count_q, zero_count_q};
      default: begin
        if (buffer_address) begin
          case (reg_addr_i[7:6])
            2'b00: reg_rdata_o = {a_q[word_index+1], a_q[word_index]};
            2'b01: reg_rdata_o = {bt_q[word_index+1], bt_q[word_index]};
            2'b10: reg_rdata_o = {c_q[word_index+1], c_q[word_index]};
            default: reg_error_o = 1'b1;
          endcase
        end else reg_error_o = 1'b1;
      end
    endcase
    if (reg_write_i && !buffer_address) reg_error_o = 1'b1;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      a_q <= '0; bt_q <= '0; c_q <= '0;
      active_q <= 1'b0; step_q <= '0; done_o <= 1'b0;
      zero_count_q <= '0; macc_count_q <= '0;
    end else begin
      done_o <= 1'b0;
      if (reg_valid_i && reg_ready_o && reg_write_i && !reg_error_o) begin
        for (int b=0; b<8; b++) if (reg_strb_i[b]) begin
          case (reg_addr_i[7:6])
            2'b00: a_q[word_index+b/4][(b%4)*8+:8] <= reg_wdata_i[b*8+:8];
            2'b01: bt_q[word_index+b/4][(b%4)*8+:8] <= reg_wdata_i[b*8+:8];
            2'b10: c_q[word_index+b/4][(b%4)*8+:8] <= reg_wdata_i[b*8+:8];
            default: ;
          endcase
        end
      end
      if (cmd_valid_i && cmd_ready_o) begin
        if (cmd_macc_i) begin
          active_q <= 1'b1; step_q <= '0;
          macc_count_q <= macc_count_q + 1;
        end else begin
          c_q <= '0; done_o <= 1'b1;
          zero_count_q <= zero_count_q + 1;
        end
      end
      if (active_q) begin
        if (pump) step_q <= step_q + 1;
        for (int col=0; col<4; col++) begin
          if (int'(step_q) >= 4+col && int'(step_q) < 8+col)
            c_q[(int'(step_q)-4-col)*4+col] <= bottom_acc[col];
        end
        if (step_q == 10) begin active_q <= 1'b0; done_o <= 1'b1; end
      end
    end
  end
endmodule
