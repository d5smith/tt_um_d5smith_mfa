/*
 * clock_divider - Parameterizable clock divider
 *
 * Produces a single-cycle registered enable pulse every `divisor` clock cycles.
 * Used to derive composition tick rates and audio sample rates
 * from the system clock.
 *
 * Behavior:
 *   - Reset: counter cleared, tick LOW
 *   - Disabled (ena=0): counter frozen, tick LOW (pause/resume)
 *   - Normal: counter increments, tick HIGH for one cycle when counter matches divisor-1
 */

module clock_divider #(
    parameter WIDTH = 24
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             ena,
    input  wire [WIDTH-1:0] divisor,
    output reg              tick
);

    reg [WIDTH-1:0] counter;

    always @(posedge clk) begin
        if (!rst_n) begin
            counter <= {WIDTH{1'b0}};
            tick    <= 1'b0;
        end else if (!ena) begin
            // Freeze: counter holds, no tick (pause/resume behavior)
            tick <= 1'b0;
        end else if (counter == divisor - 1) begin
            counter <= {WIDTH{1'b0}};
            tick    <= 1'b1;
        end else begin
            counter <= counter + 1'b1;
            tick    <= 1'b0;
        end
    end

endmodule
