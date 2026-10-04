// SPDX-License-Identifier: Apache-2.0
// Serial matrix commands share CVA6's existing non-speculative Ara port.
module matrix_router #(
  parameter type cpu_req_t = logic,
  parameter type cpu_resp_t = logic,
  parameter int TransIdWidth = 3
) (
  input logic clk_i, rst_ni,
  input cpu_req_t cpu_req_i, output cpu_resp_t cpu_resp_o,
  output cpu_req_t ara_req_o, input cpu_resp_t ara_resp_i,
  input logic ara_idle_i,
  output logic cmd_valid_o, cmd_macc_o,
  input logic cmd_ready_i, done_i
);
  logic active_q, complete_q;
  logic [TransIdWidth-1:0] id_q;
  logic [1:0] quiet_q;
  logic matrix_request;
  assign matrix_request = cpu_req_i.acc_req.insn[6:0] == 7'h2b;
  // Several quiet cycles cover the registered dispatcher -> sequencer boundary.
  // The idle input also excludes a pending backend request and vector stores.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) quiet_q <= '0;
    else if (!ara_idle_i || ara_req_o.acc_req.req_valid || ara_resp_i.acc_resp.resp_valid)
      quiet_q <= '0;
    else if (quiet_q != 3) quiet_q <= quiet_q+1;
  end
  assign cmd_valid_o = cpu_req_i.acc_req.req_valid && matrix_request &&
    !active_q && !complete_q && (&quiet_q) && !cpu_req_i.acc_req.store_pending;
  assign cmd_macc_o = cpu_req_i.acc_req.insn[25];
  always_comb begin
    ara_req_o = cpu_req_i;
    ara_req_o.acc_req.req_valid = cpu_req_i.acc_req.req_valid && !matrix_request && !active_q && !complete_q;
    cpu_resp_o = ara_resp_i; // Always preserve MMU, memory completion and fflags.
    if (matrix_request || active_q || complete_q) begin
      cpu_resp_o.acc_resp.req_ready = cmd_valid_o && cmd_ready_i;
      cpu_resp_o.acc_resp.resp_valid = complete_q;
      cpu_resp_o.acc_resp.result = '0;
      cpu_resp_o.acc_resp.trans_id = id_q;
      cpu_resp_o.acc_resp.exception = '0;
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin active_q<=0; complete_q<=0; id_q<='0; end
    else begin
      if (cmd_valid_o && cmd_ready_i) begin
        active_q<=1; id_q<=cpu_req_i.acc_req.trans_id;
      end
      if (active_q && done_i) begin active_q<=0; complete_q<=1; end
      if (complete_q && cpu_req_i.acc_req.resp_ready) complete_q<=0;
    end
  end
`ifndef SYNTHESIS
  integer event_file;
  longint unsigned cycle_q = 0;
  initial begin
    event_file = $fopen("matrix-events.csv", "w");
    $fwrite(event_file,"cycle,event,transaction,operation\n");
  end
  always @(posedge clk_i) if (rst_ni) begin
    cycle_q <= cycle_q+1;
    if (cmd_valid_o && cmd_ready_i)
      $fwrite(event_file,"%0d,issue,%0d,%0d\n",cycle_q,cpu_req_i.acc_req.trans_id,cmd_macc_o);
    if (active_q && done_i) $fwrite(event_file,"%0d,done,%0d,-\n",cycle_q,id_q);
    if (complete_q && cpu_req_i.acc_req.resp_ready)
      $fwrite(event_file,"%0d,response,%0d,-\n",cycle_q,id_q);
    if (done_i && !active_q) $fatal(1,"matrix completion without active command");
    if ((active_q || complete_q) && ara_resp_i.acc_resp.resp_valid)
      $fatal(1,"Ara/matrix response collision");
  end
  final $fclose(event_file);
`endif
endmodule
