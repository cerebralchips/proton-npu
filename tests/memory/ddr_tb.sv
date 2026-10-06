// SPDX-License-Identifier: Apache-2.0
`include "axi/typedef.svh"
module ddr_tb;
  typedef logic [63:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [4:0] id_t;
  typedef logic user_t;
  `AXI_TYPEDEF_ALL(bus, addr_t, id_t, data_t, strb_t, user_t)
  bit clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  bus_req_t req;
  bus_resp_t resp;
  proton_ddr_sim #(.req_t(bus_req_t), .resp_t(bus_resp_t), .IdWidth(5)) dut (
    .clk_i(clk), .rst_ni(rst_n), .req_i(req), .resp_o(resp));
  localparam logic [63:0] Base = 64'h100000000, End = 64'h200000000;
  int reads = 0, writes = 0;
  // AW and W arrive independently; every response is deliberately backpressured.
  task automatic write_burst(input addr_t address, input int beats,
      input data_t seed, input strb_t mask, input logic [1:0] response=0);
    fork
      begin
        @(negedge clk);
        req.aw = '0; req.aw.addr = address; req.aw.id = 5'h15;
        req.aw.len = 8'(beats-1); req.aw.size = 3; req.aw.burst = axi_pkg::BURST_INCR;
        req.aw_valid = 1;
        do @(posedge clk); while (!resp.aw_ready);
        @(negedge clk); req.aw_valid = 0;
      end
      begin
        repeat (3) @(negedge clk);
        for (int b=0; b<beats; b++) begin
          req.w.data = seed + 64'(b); req.w.strb = mask;
          req.w.last = (b == beats-1); req.w_valid = 1;
          do @(posedge clk); while (!resp.w_ready);
          @(negedge clk); req.w_valid = 0;
        end
      end
    join
    do @(posedge clk); while (!resp.b_valid);
    repeat (5) begin
      if (!resp.b_valid || resp.b.id != 5'h15 || resp.b.resp != response)
        $fatal(1, "B response changed under backpressure or was incorrect");
      @(posedge clk);
    end
    @(negedge clk); req.b_ready = 1;
    @(posedge clk); @(negedge clk); req.b_ready = 0;
    writes++;
  endtask
  task automatic read_burst(input addr_t address, input int beats,
      input data_t seed, input logic [1:0] response=0);
    bus_r_chan_t held;
    @(negedge clk);
    req.ar = '0; req.ar.addr = address; req.ar.id = 5'h0b;
    req.ar.len = 8'(beats-1); req.ar.size = 3; req.ar.burst = axi_pkg::BURST_INCR;
    req.ar_valid = 1;
    do @(posedge clk); while (!resp.ar_ready);
    @(negedge clk); req.ar_valid = 0;
    for (int b=0; b<beats; b++) begin
      do @(posedge clk); while (!resp.r_valid);
      held = resp.r;
      if (held.id != 5'h0b || held.resp != response || held.last != (b==beats-1))
        $fatal(1, "Incorrect R ID/response/last");
      if (response == 0 && held.data != seed + 64'(b))
        $fatal(1, "Read mismatch address=%h beat=%0d got=%h", address, b, held.data);
      repeat (4) begin
        @(posedge clk);
        if (!resp.r_valid || resp.r !== held) $fatal(1, "R changed under backpressure");
      end
      @(negedge clk); req.r_ready = 1;
      @(posedge clk); @(negedge clk); req.r_ready = 0;
      reads++;
    end
  endtask
  initial begin
    req = '0;
    repeat (4) @(negedge clk); rst_n = 1;
    read_burst(Base+64'h4000,1,0); // unwritten sparse memory
    write_burst(Base,16,64'hfedcba9876543200,8'hff);
    read_burst(Base,16,64'hfedcba9876543200);
    write_burst(End-8,1,64'h1122334455667788,8'hff);
    write_burst(End-8,1,64'hffeeddccbbaa0099,8'h5a);
    read_burst(End-8,1,64'h11ee33ccbb660088);
    write_burst(End-8,1,0,0); // no byte enabled
    read_burst(End-8,1,64'h11ee33ccbb660088);
    read_burst(Base-8,1,0,axi_pkg::RESP_SLVERR);
    read_burst(End,1,0,axi_pkg::RESP_SLVERR);
    write_burst(End,1,64'hdeadbeef,8'hff,axi_pkg::RESP_SLVERR);
    write_burst(Base-8,1,64'hdeadbeef,8'hff,axi_pkg::RESP_SLVERR);
    read_burst(Base,16,64'hfedcba9876543200);
    read_burst(End-8,1,64'h11ee33ccbb660088);
    // Reset clears bus state, preserving backing storage like external RAM.
    @(negedge clk); rst_n = 0;
    repeat (4) @(negedge clk); rst_n = 1;
    read_burst(End-8,1,64'h11ee33ccbb660088);
    $display("DDR UNIT PASS reads=%0d writes=%0d: bursts, IDs, AW/W skew, strobes, errors, R/B backpressure, reset", reads, writes);
    $finish;
  end
  initial begin #200000; $fatal(1, "DDR unit timeout"); end
endmodule
