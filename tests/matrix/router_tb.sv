module router_tb;
  typedef struct packed {logic req_valid,resp_ready,store_pending; logic [31:0] insn; logic [2:0] trans_id;} command_t;
  typedef struct packed {command_t acc_req; logic [7:0] acc_mmu_resp;} req_t;
  typedef struct packed {logic req_ready,resp_valid; logic [63:0] result;
    logic [2:0] trans_id; logic [7:0] exception;
    logic load_complete,store_complete,store_pending,fflags_valid;} response_t;
  typedef struct packed {response_t acc_resp; logic [7:0] acc_mmu_req;} rsp_t;
  logic clk=0,rst=0,idle=0,cv,cm,cr=0,done=0;
  always #5 clk=~clk;
  req_t cpu='0,ara;
  rsp_t back='0,resp;
  matrix_router #(.cpu_req_t(req_t),.cpu_resp_t(rsp_t)) dut(
    .clk_i(clk),.rst_ni(rst),.cpu_req_i(cpu),.cpu_resp_o(resp),
    .ara_req_o(ara),.ara_resp_i(back),.ara_idle_i(idle),
    .cmd_valid_o(cv),.cmd_macc_o(cm),.cmd_ready_i(cr),.done_i(done));
  initial begin
    repeat(3) @(negedge clk); rst=1;
    cpu.acc_req.req_valid=1; cpu.acc_req.insn='h57; back.acc_resp.req_ready=1;
    #1; if(!ara.acc_req.req_valid || !resp.acc_resp.req_ready || cv) $fatal(1,"RVV pass-through");
    @(negedge clk); cpu.acc_req.insn='h0200002b; cpu.acc_req.trans_id=5;
    cpu.acc_req.store_pending=1;
    repeat(4) begin #1; if(cv || ara.acc_req.req_valid) $fatal(1,"issued with Ara busy"); @(negedge clk); end
    idle=1;
    repeat(5) @(negedge clk);
    if(cv) $fatal(1,"issued with scalar store pending");
    cpu.acc_req.store_pending=0;
    repeat(3) begin #1; if(!cv || !cm || resp.acc_resp.req_ready) $fatal(1,"request backpressure"); @(negedge clk); end
    cr=1; @(negedge clk); cpu.acc_req.req_valid=0;
    back.acc_resp.load_complete=1; back.acc_resp.fflags_valid=1; back.acc_mmu_req='ha5;
    #1; if(!resp.acc_resp.load_complete || !resp.acc_resp.fflags_valid || resp.acc_mmu_req!='ha5)
      $fatal(1,"sidebands lost");
    done=1; @(negedge clk); done=0;
    repeat(5) begin
      #1; if(!resp.acc_resp.resp_valid || resp.acc_resp.trans_id!=5 || resp.acc_resp.result!=0 || cv)
        $fatal(1,"completion/ID/backpressure");
      @(negedge clk);
    end
    cpu.acc_req.resp_ready=1; @(negedge clk);
    #1; if(resp.acc_resp.resp_valid) $fatal(1,"duplicate response");
    $display("GATE ROUTER PASS: RVV routing, drain, sidebands, transaction ID, response backpressure");
    $finish;
  end
  initial begin #2000; $fatal(1,"router timeout"); end
endmodule
