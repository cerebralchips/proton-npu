// SPDX-License-Identifier: Apache-2.0
// Single-channel, single-element AXI DMA. No descriptors, interrupts or coherence.
module proton_dma #(
  parameter type lite_req_t = logic,
  parameter type lite_resp_t = logic,
  parameter type axi_req_t = logic,
  parameter type axi_resp_t = logic
)(
  input logic clk_i, rst_ni,
  input lite_req_t cfg_req_i, output lite_resp_t cfg_resp_o,
  output axi_req_t mem_req_o, input axi_resp_t mem_resp_i
);
  typedef enum logic [2:0] {IDLE, READ_ADDR, READ_DATA, WRITE_DATA, WRITE_RESP} state_t;
  state_t state_q;
  logic [63:0] src_q, dst_q, shape_q, stride_q;
  logic [63:0] src_addr_q, dst_addr_q, src_row_q, dst_row_q, data_q;
  logic [63:0] bytes_q, fault_q;
  logic [15:0] row_q, col_q;
  logic [1:0] size_q;
  logic transpose_q, done_q, error_q;
  logic [7:0] error_code_q;
  logic aw_sent_q, w_sent_q;
  // Independent AW/W buffering and held AXI-Lite responses.
  logic cfg_aw_q, cfg_w_q, cfg_b_q, cfg_r_q;
  logic [11:0] cfg_addr_q;
  logic [63:0] cfg_data_q, cfg_rdata_q, reg_data, merged;
  logic [7:0] cfg_strb_q;
  logic cfg_berr_q, cfg_rerr_q, wr, rd, bad_write, bad_read;
  logic [11:0] reg_addr;
  logic busy, start, clear, valid_config;
  logic [63:0] elem, src_span, dst_span;
  logic [64:0] src_end, dst_end;
  logic [31:0] src_stride, dst_stride;
  logic [15:0] rows, cols;
  assign busy = state_q != IDLE;
  assign rows = shape_q[15:0];
  assign cols = shape_q[31:16];
  assign src_stride = stride_q[31:0];
  assign dst_stride = stride_q[63:32];
  assign wr = cfg_aw_q && cfg_w_q && !cfg_b_q;
  assign rd = cfg_req_i.ar_valid && cfg_resp_o.ar_ready;
  assign reg_addr = wr ? cfg_addr_q : cfg_req_i.ar.addr[11:0];
  // Register writes are byte-masked at aligned 64-bit addresses.
  always_comb begin
    reg_data = '0;
    bad_read = 0;
    case (reg_addr)
      'h00: reg_data = 64'h0001_0000_444d4131; // ABI 1, DMA1
      'h08: reg_data = {48'b0,error_code_q,5'b0,error_q,done_q,busy};
      'h10: reg_data = src_q;
      'h18: reg_data = dst_q;
      'h20: reg_data = shape_q;
      'h28: reg_data = stride_q;
      'h30: reg_data = '0;
      'h38: reg_data = bytes_q;
      'h40: reg_data = fault_q;
      default: bad_read = 1;
    endcase
    merged = reg_data;
    for (int b=0;b<8;b++) if (cfg_strb_q[b]) merged[b*8+:8] = cfg_data_q[b*8+:8];
    bad_write = busy || !(reg_addr inside {'h10,'h18,'h20,'h28,'h30});
    if (reg_addr=='h30 && ((merged & ~64'h1f)!=0 || (merged[0] && merged[4]))) bad_write=1;
  end
  assign start = wr && !bad_write && reg_addr=='h30 && merged[0];
  assign clear = wr && !bad_write && reg_addr=='h30 && merged[4];
  assign elem = 64'd1 << merged[3:2];
  // 16-bit dimensions * 32-bit strides cannot overflow 64-bit spans.
  assign src_span = (64'(rows)-1)*64'(src_stride) + 64'(cols)*elem;
  assign dst_span = merged[1] ? (64'(cols)-1)*64'(dst_stride) + 64'(rows)*elem :
                                              (64'(rows)-1)*64'(dst_stride) + 64'(cols)*elem;
  assign src_end = {1'b0,src_q} + {1'b0,src_span};
  assign dst_end = {1'b0,dst_q} + {1'b0,dst_span};
  function automatic logic in_sram(logic [63:0] base, logic [64:0] limit);
    return base>=64'h80000000 && limit<=65'h81000000;
  endfunction
  function automatic logic in_ddr(logic [63:0] base, logic [64:0] limit);
    return base>=64'h100000000 && limit<=65'h200000000;
  endfunction
  assign valid_config = rows!=0 && cols!=0 && shape_q[63:32]==0 &&
    ((src_q|dst_q|64'(src_stride)|64'(dst_stride)) & (elem-1))==0 &&
    64'(src_stride)>=64'(cols)*elem &&
    64'(dst_stride)>=(merged[1] ? 64'(rows) : 64'(cols))*elem &&
    ((in_sram(src_q,src_end) && in_ddr(dst_q,dst_end)) ||
     (in_ddr(src_q,src_end) && in_sram(dst_q,dst_end)));

  always_comb begin
    cfg_resp_o = '0;
    cfg_resp_o.aw_ready = !cfg_aw_q && !cfg_b_q;
    cfg_resp_o.w_ready = !cfg_w_q && !cfg_b_q;
    cfg_resp_o.b_valid = cfg_b_q;
    cfg_resp_o.b.resp = cfg_berr_q ? 2'b10 : 2'b00;
    cfg_resp_o.ar_ready = !cfg_r_q && !wr;
    cfg_resp_o.r_valid = cfg_r_q;
    cfg_resp_o.r.data = cfg_rdata_q;
    cfg_resp_o.r.resp = cfg_rerr_q ? 2'b10 : 2'b00;
    mem_req_o = '0;
    mem_req_o.ar_valid = state_q==READ_ADDR;
    mem_req_o.ar.addr = src_addr_q;
    mem_req_o.ar.size = {1'b0,size_q};
    mem_req_o.ar.burst = 2'b01;
    mem_req_o.r_ready = state_q==READ_DATA;
    mem_req_o.aw_valid = state_q==WRITE_DATA && !aw_sent_q;
    mem_req_o.aw.addr = dst_addr_q;
    mem_req_o.aw.size = {1'b0,size_q};
    mem_req_o.aw.burst = 2'b01;
    mem_req_o.w_valid = state_q==WRITE_DATA && !w_sent_q;
    mem_req_o.w.data = data_q << (dst_addr_q[2:0]*8);
    mem_req_o.w.strb = 8'((32'd1 << (32'd1<<size_q))-32'd1) << dst_addr_q[2:0];
    mem_req_o.w.last = 1;
    mem_req_o.b_ready = state_q==WRITE_RESP;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cfg_aw_q<=0; cfg_w_q<=0; cfg_b_q<=0; cfg_r_q<=0;
      cfg_addr_q<=0; cfg_data_q<=0; cfg_strb_q<=0; cfg_rdata_q<=0;
      cfg_berr_q<=0; cfg_rerr_q<=0;
      src_q<=0; dst_q<=0; shape_q<=0; stride_q<=0;
      state_q<=IDLE; src_addr_q<=0; dst_addr_q<=0; src_row_q<=0; dst_row_q<=0;
      row_q<=0; col_q<=0; size_q<=0; transpose_q<=0; data_q<=0;
      bytes_q<=0; fault_q<=0; error_code_q<=0; done_q<=0; error_q<=0;
      aw_sent_q<=0; w_sent_q<=0;
    end else begin
      if (cfg_req_i.aw_valid && cfg_resp_o.aw_ready) begin cfg_aw_q<=1; cfg_addr_q<=cfg_req_i.aw.addr[11:0]; end
      if (cfg_req_i.w_valid && cfg_resp_o.w_ready) begin cfg_w_q<=1; cfg_data_q<=cfg_req_i.w.data; cfg_strb_q<=cfg_req_i.w.strb; end
      if (cfg_b_q && cfg_req_i.b_ready) cfg_b_q<=0;
      if (cfg_r_q && cfg_req_i.r_ready) cfg_r_q<=0;
      if (rd) begin cfg_r_q<=1; cfg_rdata_q<=reg_data; cfg_rerr_q<=bad_read; end
      if (wr) begin
        cfg_aw_q<=0; cfg_w_q<=0; cfg_b_q<=1; cfg_berr_q<=bad_write;
        if (!bad_write) case (reg_addr)
          'h10: src_q<=merged;
          'h18: dst_q<=merged;
          'h20: shape_q<=merged;
          'h28: stride_q<=merged;
          default: ;
        endcase
      end
      if (clear) begin done_q<=0; error_q<=0; error_code_q<=0; bytes_q<=0; fault_q<=0; end
      if (start) begin
        bytes_q<=0; fault_q<=0; error_code_q<=0; done_q<=0; error_q<=0;
        if (!valid_config) begin done_q<=1; error_q<=1; error_code_q<=1; end
        else begin
          src_addr_q<=src_q; dst_addr_q<=dst_q; src_row_q<=src_q; dst_row_q<=dst_q;
          row_q<=0; col_q<=0; size_q<=merged[3:2]; transpose_q<=merged[1];
          state_q<=READ_ADDR;
        end
      end
      case (state_q)
        READ_ADDR: if (mem_resp_i.ar_ready) state_q<=READ_DATA;
        READ_DATA: if (mem_resp_i.r_valid) begin
          if (mem_resp_i.r.resp!=0 || !mem_resp_i.r.last || mem_resp_i.r.id!=0) begin
            state_q<=IDLE; done_q<=1; error_q<=1; error_code_q<=2; fault_q<=src_addr_q;
          end else begin
            data_q<=mem_resp_i.r.data >> (src_addr_q[2:0]*8);
            aw_sent_q<=0; w_sent_q<=0; state_q<=WRITE_DATA;
          end
        end
        WRITE_DATA: begin
          if (mem_resp_i.aw_ready) aw_sent_q<=1;
          if (mem_resp_i.w_ready) w_sent_q<=1;
          if ((aw_sent_q || mem_resp_i.aw_ready) && (w_sent_q || mem_resp_i.w_ready)) state_q<=WRITE_RESP;
        end
        WRITE_RESP: if (mem_resp_i.b_valid) begin
          if (mem_resp_i.b.resp!=0 || mem_resp_i.b.id!=0) begin
            state_q<=IDLE; done_q<=1; error_q<=1; error_code_q<=3; fault_q<=dst_addr_q;
          end else begin
            bytes_q<=bytes_q+(64'd1<<size_q);
            if (col_q==cols-1) begin
              col_q<=0; row_q<=row_q+1;
              src_row_q<=src_row_q+64'(src_stride); src_addr_q<=src_row_q+64'(src_stride);
              dst_row_q<=dst_row_q+(transpose_q ? (64'd1<<size_q) : 64'(dst_stride));
              dst_addr_q<=dst_row_q+(transpose_q ? (64'd1<<size_q) : 64'(dst_stride));
              if (row_q==rows-1) begin state_q<=IDLE; done_q<=1; end
              else state_q<=READ_ADDR;
            end else begin
              col_q<=col_q+1; src_addr_q<=src_addr_q+(64'd1<<size_q);
              dst_addr_q<=dst_addr_q+(transpose_q ? 64'(dst_stride) : (64'd1<<size_q));
              state_q<=READ_ADDR;
            end
          end
        end
        default: ;
      endcase
    end
  end
  // Named probes for independent waveform reconstruction (not a data source).
  wire check_ar_valid=mem_req_o.ar_valid, check_ar_ready=mem_resp_i.ar_ready;
  wire [63:0] check_ar_addr=mem_req_o.ar.addr;
  wire [2:0] check_ar_size=mem_req_o.ar.size;
  wire check_r_valid=mem_resp_i.r_valid, check_r_ready=mem_req_o.r_ready;
  wire [63:0] check_r_data=mem_resp_i.r.data;
  wire [1:0] check_r_resp=mem_resp_i.r.resp;
  wire check_r_last=mem_resp_i.r.last;
  wire check_aw_valid=mem_req_o.aw_valid, check_aw_ready=mem_resp_i.aw_ready;
  wire [63:0] check_aw_addr=mem_req_o.aw.addr;
  wire [2:0] check_aw_size=mem_req_o.aw.size;
  wire check_w_valid=mem_req_o.w_valid, check_w_ready=mem_resp_i.w_ready;
  wire [63:0] check_w_data=mem_req_o.w.data;
  wire [7:0] check_w_strb=mem_req_o.w.strb;
  wire check_w_last=mem_req_o.w.last;
  wire check_b_valid=mem_resp_i.b_valid, check_b_ready=mem_req_o.b_ready;
  wire [1:0] check_b_resp=mem_resp_i.b.resp;
  // Assertions remain enabled in the dedicated DMA unit build.
  assert property (@(posedge clk_i) disable iff(!rst_ni)
    mem_req_o.ar_valid && !mem_resp_i.ar_ready |=> mem_req_o.ar_valid && $stable(mem_req_o.ar));
  assert property (@(posedge clk_i) disable iff(!rst_ni)
    mem_req_o.aw_valid && !mem_resp_i.aw_ready |=> mem_req_o.aw_valid && $stable(mem_req_o.aw));
  assert property (@(posedge clk_i) disable iff(!rst_ni)
    mem_req_o.w_valid && !mem_resp_i.w_ready |=> mem_req_o.w_valid && $stable(mem_req_o.w));
endmodule
