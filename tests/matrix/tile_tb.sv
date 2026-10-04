module tile_tb;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0, valid=0, macc=0, ready, done, busy;
  logic rv=0, wr=0, rr, err;
  logic [11:0] addr=0;
  logic [63:0] wd=0, rd;
  logic [7:0] strb=0;
  logic [31:0] vectors [0:16383];
  logic [31:0] pd=0, pw=0, pa=0, po;
  integer signed expected;
  matrix_tile dut(.clk_i(clk),.rst_ni(rst),.cmd_valid_i(valid),.cmd_macc_i(macc),
    .cmd_ready_o(ready),.done_o(done),.busy_o(busy),.reg_valid_i(rv),.reg_write_i(wr),
    .reg_addr_i(addr),.reg_wdata_i(wd),.reg_strb_i(strb),.reg_ready_o(rr),
    .reg_error_o(err),.reg_rdata_o(rd));
  quadrilatero_mac_int #(.ENABLE_SIMD(1)) mac(.data_i(pd),.weight_i(pw),.acc_i(pa),
    .op_datatype_i(quadrilatero_pkg::SIZE_8),.mac_finished_o(),.acc_o(po));
  task automatic write_reg(input int a, input logic [63:0] d, input logic [7:0] be=8'hff);
    @(negedge clk); rv=1; wr=1; addr=12'(a); wd=d; strb=be;
    #1; if (!rr || err) $fatal(1,"register write rejected");
    @(negedge clk); rv=0; wr=0;
  endtask
  task automatic check_reg(input int a, input logic [63:0] expected_value);
    @(negedge clk); addr=12'(a); rv=1; wr=0;
    #1; if (!rr || err || rd !== expected_value)
      $fatal(1,"read %x got %x expected %x",a,rd,expected_value);
    @(negedge clk); rv=0;
  endtask
  task automatic command(input logic op);
    @(negedge clk); valid=1; macc=op;
    #1; if (!ready) $fatal(1,"command not ready");
    @(negedge clk); valid=0;
    for (int t=0;t<30;t++) begin
      if (done) return;
      if (op && (!busy || rr || ready)) $fatal(1,"busy exclusion broken");
      @(negedge clk);
    end
    $fatal(1,"command timeout");
  endtask
  initial begin
    string vector_file;
    if (!$value$plusargs("vectors=%s",vector_file)) $fatal(1,"missing vectors");
    $readmemh(vector_file,vectors);
    repeat(3) @(negedge clk); rst=1;
    // Exhaust all signed INT8 pairs independently in each packed byte lane.
    for (int lane=0;lane<4;lane++) for(int x=-128;x<128;x++) for(int y=-128;y<128;y++) begin
      pd=32'($unsigned(8'(x))) << (lane*8); pw=32'($unsigned(8'(y))) << (lane*8);
      pa=32'h7fffffff; expected=x*y; #1;
      if(po !== (32'h7fffffff+32'(expected))) $fatal(1,"PE signed/overflow mismatch lane=%0d x=%0d y=%0d pd=%x pw=%x got=%x",lane,x,y,pd,pw,po);
    end
    $display("GATE PE PASS: 262144 lane/pair cases including overflow");
    check_reg('h0,64'h0001_0410_4d41_5431);
    write_reg('h100,64'h1122334455667788);
    write_reg('h100,64'haabbccddeeff0011,8'b01010101);
    check_reg('h100,64'h11bb33dd55ff7711);
    @(negedge clk); rv=1; wr=1; addr=0; #1;
    if(!err) $fatal(1,"ID must be read-only");
    @(negedge clk); wr=0; addr='h200; #1;
    if(!err) $fatal(1,"invalid address must fail");
    @(negedge clk); rv=0;
    for(int test=0;test<256;test++) begin
      for(int w=0;w<48;w+=2) write_reg('h100+w*4,{vectors[test*64+w+1],vectors[test*64+w]});
      command(1);
      for(int w=0;w<16;w+=2)
        check_reg('h180+w*4,{vectors[test*64+48+w+1],vectors[test*64+48+w]});
      command(0);
      for(int w=0;w<16;w+=2) check_reg('h180+w*4,0);
    end
    check_reg('h10,{32'd256,32'd256});
    // Reset in the middle of an operation cancels it and clears all visible state.
    @(negedge clk); valid=1; macc=1;
    @(negedge clk); valid=0;
    repeat(3) @(negedge clk); rst=0;
    repeat(2) @(negedge clk); rst=1;
    check_reg('h10,0); check_reg('h180,0);
    #1; if(busy || done || !ready) $fatal(1,"reset did not cancel command");
    $display("GATE TILE PASS: 256 random/directed cases, byte enables, decode, zero, reset, bounded completion");
    $finish;
  end
  initial begin #2000000; $fatal(1,"global timeout"); end
endmodule
