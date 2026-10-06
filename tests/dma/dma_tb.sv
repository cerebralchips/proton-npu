// SPDX-License-Identifier: Apache-2.0
`include "axi/typedef.svh"
module dma_tb;
  typedef logic [63:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [4:0] id_t;
  typedef logic user_t;
  `AXI_TYPEDEF_ALL(bus, addr_t, id_t, data_t, strb_t, user_t)
  `AXI_LITE_TYPEDEF_ALL(cfg, addr_t, data_t, strb_t)
  bit clk=0, rst_n=0;
  always #5 clk=~clk;
  cfg_req_t cfg='0;
  cfg_resp_t rsp;
  bus_req_t req;
  bus_resp_t resp;
  proton_dma #(.lite_req_t(cfg_req_t),.lite_resp_t(cfg_resp_t),
    .axi_req_t(bus_req_t),.axi_resp_t(bus_resp_t)) dut(
    .clk_i(clk),.rst_ni(rst_n),.cfg_req_i(cfg),.cfg_resp_o(rsp),.mem_req_o(req),.mem_resp_i(resp));
  byte unsigned mem [longint unsigned];
  int cycle=0, reads=0, writes=0, tests=0;
  int read_error=0, write_error=0;
  bit freeze=0, have_ar=0, have_aw=0, have_w=0;
  int rdelay=0,bdelay=0;
  addr_t ra,wa;
  bus_w_chan_t wd;
  always_comb begin
    resp='0;
    resp.ar_ready=!freeze && !have_ar && cycle%4==0;
    resp.aw_ready=!freeze && !have_aw && cycle%5==0;
    resp.w_ready=!freeze && !have_w && cycle%3==0;
    resp.r_valid=have_ar && rdelay==0;
    resp.r.resp=read_error==1 ? 2 : 0;
    resp.r.id=read_error==2 ? 1 : 0;
    resp.r.last=read_error!=3;
    for(int b=0;b<8;b++)
      resp.r.data[b*8+:8]=(mem.exists((ra&~64'd7)+64'(b))!=0) ? mem[(ra&~64'd7)+64'(b)] : 0;
    resp.b_valid=have_aw && have_w && bdelay==0;
    resp.b.resp=write_error==1 ? 2 : 0;
    resp.b.id=write_error==2 ? 1 : 0;
  end
  always @(posedge clk) begin
    cycle<=cycle+1;
    if(!rst_n) begin have_ar<=0;have_aw<=0;have_w<=0;rdelay<=0;bdelay<=0; end
    else begin
      if(rdelay>0) rdelay<=rdelay-1;
      if(bdelay>0) bdelay<=bdelay-1;
      if(req.ar_valid && resp.ar_ready) begin
        if(req.ar.len!=0 || req.ar.size>3 || req.ar.id!=0) $fatal(1,"bad AR");
        have_ar<=1;ra<=req.ar.addr;rdelay<=4;reads<=reads+1;
      end
      if(req.r_ready && resp.r_valid) have_ar<=0;
      if(req.aw_valid && resp.aw_ready) begin
        if(req.aw.len!=0 || req.aw.size>3 || req.aw.id!=0) $fatal(1,"bad AW");
        have_aw<=1;wa<=req.aw.addr;bdelay<=4;
      end
      if(req.w_valid && resp.w_ready) begin
        if(!req.w.last) $fatal(1,"missing WLAST");
        have_w<=1;wd<=req.w;bdelay<=4;
      end
      if(req.b_ready && resp.b_valid) begin
        for(int b=0;b<8;b++) if(wd.strb[b]) mem[(wa&~64'd7)+64'(b)]=wd.data[b*8+:8];
        have_aw<=0;have_w<=0;writes<=writes+1;
      end
    end
  end
  task automatic put(input int a,input data_t d,input bit error=0,input strb_t mask=8'hff);
    bit first;
    first=1'(cycle%2);
    @(negedge clk);cfg.aw.addr=64'(a);cfg.w.data=d;cfg.w.strb=mask;
    if(first) cfg.w_valid=1; else cfg.aw_valid=1;
    do @(posedge clk); while(first ? !rsp.w_ready : !rsp.aw_ready);
    @(negedge clk);cfg.aw_valid=0;cfg.w_valid=0;
    repeat(3) @(negedge clk);
    if(first) cfg.aw_valid=1; else cfg.w_valid=1;
    do @(posedge clk); while(first ? !rsp.aw_ready : !rsp.w_ready);
    @(negedge clk);cfg.aw_valid=0;cfg.w_valid=0;
    while(!rsp.b_valid) @(negedge clk);
    repeat(3) begin
      if(!rsp.b_valid || rsp.b.resp!=(error ? 2 : 0)) $fatal(1,"bad cfg B %h",a);
      @(negedge clk);
    end
    cfg.b_ready=1;@(negedge clk);cfg.b_ready=0;
  endtask
  task automatic get(input int a,output data_t d,input bit error=0);
    @(negedge clk);cfg.ar.addr=64'(a);cfg.ar_valid=1;
    do @(posedge clk); while(!rsp.ar_ready);
    @(negedge clk);cfg.ar_valid=0;
    while(!rsp.r_valid) @(negedge clk);
    d=rsp.r.data;
    repeat(3) begin
      if(!rsp.r_valid || rsp.r.data!==d || rsp.r.resp!=(error ? 2 : 0)) $fatal(1,"bad cfg R");
      @(negedge clk);
    end
    cfg.r_ready=1;@(negedge clk);cfg.r_ready=0;
  endtask
  task automatic setup(input addr_t s,d,input int rows,cols,ss,ds);
    put('h10,s);put('h18,d);put('h20,(64'(cols)<<16)|64'(rows));put('h28,(64'(ds)<<32)|64'(ss));
  endtask
  task automatic finish_check(input int error,input int bytes);
    data_t v;
    do get('h08,v); while(v[0]);
    if(!v[1] || v[2]!=(error!=0) || v[15:8]!=8'(error)) $fatal(1,"status %h expected %d",v,error);
    get('h38,v);if(v!=64'(bytes)) $fatal(1,"bytes %d expected %d",v,bytes);
    tests++;
  endtask
  task automatic transfer(input int size,input bit tr,reverse,input int rows,cols,input int lane);
    addr_t s,d;
    int e,ss,ds;
    e=1<<size; ss=(cols+2)*e;ds=((tr?rows:cols)+3)*e;
    s=(reverse ? 64'h100001000 : 64'h80001000)+64'(lane*e);
    d=(reverse ? 64'h80008000 : 64'h100008000)+64'(32'(((lane+1)%(8/e))*e));
    for(int i=0;i<1024;i++) begin mem[s+64'(i)]=8'(i*17+size+7);mem[d+64'(i)]=8'hcd;end
    setup(s,d,rows,cols,ss,ds);
    put('h30,1|(64'(tr)<<1)|(64'(size)<<2));
    finish_check(0,rows*cols*e);
    for(int i=0;i<1024;i++) begin
      byte unsigned expected;
      expected=8'hcd;
      for(int rr=0;rr<rows;rr++) for(int cc=0;cc<cols;cc++) for(int b=0;b<e;b++)
        if(i==(tr ? cc*ds+rr*e+b : rr*ds+cc*e+b)) expected=8'((rr*ss+cc*e+b)*17+size+7);
      if(mem[d+64'(i)]!==expected) $fatal(1,"copy/transpose size%0d tr%0d dir%0d byte%0d",size,tr,reverse,i);
    end
  endtask
  initial begin
    data_t v;
    int before_reads;
    repeat(5) @(negedge clk);rst_n=1;
    get(0,v);if(v!=64'h00010000444d4131) $fatal(1,"ID");
    put('h10,64'h1122334455667788);put('h10,64'hab,0,1);get('h10,v);
    if(v!=64'h11223344556677ab) $fatal(1,"byte strobes");
    put('h00,0,1);put('h11,0,1);get('h48,v,1);
    for(int size=0;size<4;size++) for(int tr=0;tr<2;tr++) for(int dir=0;dir<2;dir++)
      for(int lane=0;lane<(8>>size);lane++) transfer(size,1'(tr),1'(dir),3,5,lane);
    transfer(0,1,0,1,7,0);transfer(1,1,1,7,1,0);transfer(3,1,0,1,1,0);
    // Boundary positives touch the final byte of each installed region.
    setup(64'h80fffff8,64'h1fffffff8,1,1,8,8);put('h30,13);finish_check(0,8);
    setup(64'h1fffffff8,64'h80fffff8,1,1,8,8);put('h30,13);finish_check(0,8);
    // Bad descriptors never issue an AXI read.
    before_reads=reads;
    setup(64'h80001000,64'h100001000,0,5,8,8);put('h30,1);finish_check(1,0);
    setup(64'h80001001,64'h100001000,1,1,8,8);put('h30,13);finish_check(1,0);
    setup(64'h80001000,64'h100001000,2,5,4,5);put('h30,1);finish_check(1,0);
    setup(64'h80001000,64'h100001000,5,2,2,4);put('h30,3);finish_check(1,0);
    setup(64'h80fffff8,64'h100001000,1,2,16,16);put('h30,13);finish_check(1,0);
    setup(64'h80001000,64'h1fffffff8,1,2,16,16);put('h30,13);finish_check(1,0);
    setup(64'hfffffffffffffff8,64'h80001000,1,2,16,16);put('h30,13);finish_check(1,0);
    setup(64'h80001000,64'h80002000,1,1,8,8);put('h30,13);finish_check(1,0);
    if(reads!=before_reads) $fatal(1,"invalid descriptor touched memory");
    // Busy reprogramming and START rejected without disrupting active transfer.
    setup(64'h80001000,64'h100001000,1,1,8,8);freeze=1;put('h30,13);
    put('h10,0,1);put('h30,13,1);get('h10,v);if(v!=64'h80001000) $fatal(1,"busy config changed");
    freeze=0;finish_check(0,8);
    for(int error=1;error<=3;error++) begin
      read_error=error;setup(64'h80001000,64'h100001000,1,1,8,8);put('h30,13);finish_check(2,0);
      get('h40,v);if(v!=64'h80001000) $fatal(1,"read fault address");
    end
    read_error=0;
    for(int error=1;error<=2;error++) begin
      write_error=error;put('h30,13);finish_check(3,0);
      get('h40,v);if(v!=64'h100001000) $fatal(1,"write fault address");
    end
    write_error=0;put('h30,16);get('h08,v);if(v!=0) $fatal(1,"clear");
    freeze=1;put('h30,13);repeat(5) @(negedge clk);rst_n=0;
    repeat(5) @(negedge clk);rst_n=1;freeze=0;
    get('h08,v);if(v!=0 || req.ar_valid || req.aw_valid || req.w_valid) $fatal(1,"reset");
    transfer(2,1,1,3,5,0);
    $display("DMA UNIT PASS checks=%0d reads=%0d writes=%0d",tests,reads,writes);$finish;
  end
  initial begin repeat(200000) @(posedge clk);$fatal(1,"DMA unit timeout");end
endmodule
