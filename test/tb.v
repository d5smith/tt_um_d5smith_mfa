/*
 * tb.v - Cocotb testbench wrapper
 *
 * Instantiates the top-level module and provides the signals
 * that cocotb will drive/read via VPI.
 */

`default_nettype none
`timescale 1ns / 1ps

module tb ();

    // Dump waveforms
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
        #1;
    end

    // Testbench signals
    reg        clk;
    reg        rst_n;
    reg        ena;
    reg  [7:0] ui_in;
    reg  [7:0] uio_in;
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    // Instantiate the DUT.
    //
    // For RTL simulation we override the production divisors with tiny values
    // so tests finish in seconds. For gate-level simulation, the synthesized
    // netlist has parameters baked in at synthesis time and exposes no
    // overrideable parameters — so we skip the override block entirely.
`ifdef GL_TEST
    supply1 VPWR;
    supply0 VGND;

    tt_um_d5smith_mfa dut (
        .VPWR    (VPWR),
        .VGND    (VGND),
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (uio_in),
        .uio_out (uio_out),
        .uio_oe  (uio_oe),
        .ena     (ena),
        .clk     (clk),
        .rst_n   (rst_n)
    );
`else
    tt_um_d5smith_mfa #(
        .SAMPLE_DIV(4),     // Sample tick every 4 clocks
        .TEMPO_SLOW(100),   // Composition tick every 100 clocks (~slow)
        .TEMPO_MED(50),     // ~medium
        .TEMPO_FAST(25),    // ~fast
        .TEMPO_VFAST(12)    // ~very fast
    ) dut (
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (uio_in),
        .uio_out (uio_out),
        .uio_oe  (uio_oe),
        .ena     (ena),
        .clk     (clk),
        .rst_n   (rst_n)
    );
`endif

endmodule
