module bus_tb;
  typedef struct packed {logic [63:0] addr; logic [2:0] prot;} addr_t;
  typedef struct packed {logic [63:0] data; logic [7:0] strb;} w_t;
  typedef struct packed {logic [1:0] resp;} b_t;
  typedef struct packed {logic [63:0] data; logic [1:0] resp;} r_t;
  typedef struct packed {addr_t aw; logic aw_valid; w_t w; logic w_valid;
    logic b_ready; addr_t ar; logic ar_valid; logic r_ready;} req_t;
  typedef struct packed {logic aw_ready,w_ready; b_t b; logic b_valid;
    logic ar_ready; r_t r; logic r_valid;} resp_t;
  logic clk=0, rst=0, cv=0, cm=0, cr, done;
  always #5 clk=~clk;
  req_t req='0;
  resp_t rsp;
  logic [63:0] model [0:23];
  matrix_axi_lite #(.req_t(req_t),.resp_t(resp_t)) dut(
    .clk_i(clk),.rst_ni(rst),.req_i(req),.resp_o(rsp),
    .cmd_valid_i(cv),.cmd_macc_i(cm),.cmd_ready_o(cr),.done_o(done));
  task automatic write_bus(input int a, input logic [63:0] d, input logic [7:0] be,
                            input bit w_first, input bit error=0);
    @(negedge clk);
    req.aw.addr=64'(a); req.w.data=d; req.w.strb=be;
    if(w_first) req.w_valid=1; else req.aw_valid=1;
    do @(posedge clk); while(w_first ? !rsp.w_ready : !rsp.aw_ready);
    @(negedge clk); req.w_valid=0; req.aw_valid=0;
    repeat(3) @(negedge clk);
    if(w_first) req.aw_valid=1; else req.w_valid=1;
    do @(posedge clk); while(w_first ? !rsp.aw_ready : !rsp.w_ready);
    @(negedge clk); req.w_valid=0; req.aw_valid=0;
    while(!rsp.b_valid) @(negedge clk);
    repeat(4) begin
      if(!rsp.b_valid || rsp.b.resp != (error?2:0)) $fatal(1,"B unstable/error response");
      @(negedge clk);
    end
    req.b_ready=1; @(negedge clk); req.b_ready=0;
  endtask
  task automatic read_bus(input int a, input logic [63:0] expected, input bit error=0);
    @(negedge clk); req.ar.addr=64'(a); req.ar_valid=1;
    do @(posedge clk); while(!rsp.ar_ready);
    @(negedge clk); req.ar_valid=0;
    while(!rsp.r_valid) @(negedge clk);
    repeat(4) begin
      if(!rsp.r_valid || rsp.r.resp != (error?2:0) || (!error && rsp.r.data!==expected))
        $fatal(1,"R unstable/mismatch addr=%x got=%x expected=%x",a,rsp.r.data,expected);
      @(negedge clk);
    end
    req.r_ready=1; @(negedge clk); req.r_ready=0;
  endtask
  initial begin
    logic [63:0] d;
    logic [7:0] be;
    int seed;
    seed=32'h12345678;
    seed=$urandom(seed);
    foreach(model[i]) model[i]=0;
    repeat(3) @(negedge clk); rst=1;
    read_bus(0,64'h000104104d415431);
    for(int i=0;i<128;i++) begin
      int n;
      n=int'($urandom_range(23,0)); d={$urandom,$urandom}; be=8'($urandom);
      write_bus('h100+n*8,d,be,1'(i));
      for(int b=0;b<8;b++) if(be[b]) model[n][b*8+:8]=d[b*8+:8];
      read_bus('h100+n*8,model[n]);
    end
    write_bus(0,0,'1,0,1); read_bus('h200,0,1);
    // A partial write must prevent a matrix command from overtaking the data.
    @(negedge clk); req.aw.addr='h100; req.aw_valid=1;
    @(negedge clk); req.aw_valid=0; cv=1; cm=0;
    repeat(3) begin #1; if(cr) $fatal(1,"command overtook partial write"); @(negedge clk); end
    req.w_valid=1; req.w.data=0; req.w.strb='1;
    @(negedge clk); req.w_valid=0; req.b_ready=1;
    do @(posedge clk); while(!cr);
    @(negedge clk); cv=0; req.b_ready=0;
    read_bus('h180,0);
    // An active compute stalls register reads, and the response appears after completion.
    @(negedge clk); cv=1; cm=1;
    do @(posedge clk); while(!cr);
    @(negedge clk); cv=0; req.ar_valid=1; req.ar.addr='h10;
    #1; if(rsp.ar_ready) $fatal(1,"register read bypassed active computation");
    do @(posedge clk); while(!rsp.ar_ready);
    @(negedge clk); req.ar_valid=0; req.r_ready=1;
    @(negedge clk); req.r_ready=0;
    // Reset discards an incomplete AXI transaction.
    req.aw_valid=1;
    @(negedge clk); req='0; rst=0;
    repeat(2) @(negedge clk); rst=1;
    read_bus('h10,0);
    $display("GATE BUS PASS: AW/W skew, strobes, R/B backpressure, errors, arbitration, busy, reset");
    $finish;
  end
  initial begin #100000; $fatal(1,"bus timeout"); end
endmodule
