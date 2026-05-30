/*
 * composition_engine - LFSR-based pseudo-random composition
 *
 * Contains three LFSRs (5-bit, 7-bit, 12-bit) with co-prime
 * maximal-length periods. Generates raw note values and
 * musical shaping signals (rest, hold).
 *
 * LFSR tick assignment:
 *   - LFSR-12: advances on comp_tick_bass
 *   - LFSR-5, LFSR-7: advance on comp_tick_melody
 *
 * Combined period: LCM(31, 127, 4095) = 16,122,015 ticks
 * At 4 Hz composition rate = ~46.6 days before full repetition.
 */

module composition_engine (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        ena,
    input  wire        comp_tick_bass,
    input  wire        comp_tick_melody,
    output wire [4:0]  lfsr5_out,
    output wire [6:0]  lfsr7_out,
    output wire [11:0] lfsr12_out,
    output wire [3:0]  bass_raw,
    output wire [3:0]  melody_raw,
    output wire        bass_rest,
    output wire        melody_rest,
    output wire        bass_hold,
    output wire        melody_hold
);

    // --- Seeds (non-zero, chosen for musical variety) ---
    localparam SEED5  = 5'b10011;
    localparam SEED7  = 7'b1100101;
    localparam SEED12 = 12'b1010_0011_0111;

    // --- LFSR registers ---
    reg [4:0]  lfsr5;
    reg [6:0]  lfsr7;
    reg [11:0] lfsr12;

    // --- Feedback bits (maximal-length polynomials) ---
    // This implementation shifts right and inserts the feedback bit at the MSB:
    //     next = {feedback, state[N-1:1]}
    // For that convention, the constant term maps to bit 0.
    // x^5 + x^3 + 1: taps at bits 0 and 2
    wire fb5 = lfsr5[0] ^ lfsr5[2];

    // x^7 + x^6 + 1: taps at bits 0 and 1
    wire fb7 = lfsr7[0] ^ lfsr7[1];

    // x^12 + x^11 + x^10 + x^4 + 1: taps at bits 0, 1, 2, and 8
    wire fb12 = lfsr12[0] ^ lfsr12[1] ^ lfsr12[2] ^ lfsr12[8];

    // --- LFSR state machine ---
    always @(posedge clk) begin
        if (!rst_n) begin
            lfsr5  <= SEED5;
            lfsr7  <= SEED7;
            lfsr12 <= SEED12;
        end else if (ena) begin
            // LFSR-5 and LFSR-7 advance on melody tick
            if (comp_tick_melody) begin
                lfsr5 <= (lfsr5 == 5'b0) ? SEED5 : {fb5, lfsr5[4:1]};
                lfsr7 <= (lfsr7 == 7'b0) ? SEED7 : {fb7, lfsr7[6:1]};
            end
            // LFSR-12 advances on bass tick
            if (comp_tick_bass) begin
                lfsr12 <= (lfsr12 == 12'b0) ? SEED12 : {fb12, lfsr12[11:1]};
            end
        end
    end

    // --- Outputs: raw LFSR states ---
    assign lfsr5_out  = lfsr5;
    assign lfsr7_out  = lfsr7;
    assign lfsr12_out = lfsr12;

    // =========================================================
    // Musical Shaping: Rest Probability
    //
    // On each composition tick, compare LFSR bits against a threshold.
    // If below threshold → voice rests (silence) for this tick.
    // Higher threshold = more rests = sparser music.
    //
    // Density modulation: LFSR-12 upper bits slowly shift the threshold.
    // Since LFSR-12 has a 4095-tick period, the upper bits change very
    // slowly — creating gradual density breathing over minutes.
    // Controlled by ENABLE_DENSITY_MOD parameter (default ON).
    // =========================================================
    localparam REST_THRESHOLD_BASE = 4'd3;  // ~19% base rest probability

    // Compile-time parameter: set to 0 to disable density modulation for area savings
    parameter ENABLE_DENSITY_MOD = 1;

    // Effective threshold: base + slow modulation from LFSR-12 upper bits (0-3 range)
    // When enabled: threshold ranges from 3 to 6 (~19% to ~38% rest probability)
    // When disabled: fixed at 3
    wire [3:0] rest_threshold = ENABLE_DENSITY_MOD
        ? (REST_THRESHOLD_BASE + {2'b0, lfsr12[11:10]})
        : REST_THRESHOLD_BASE;

    // Combinational rest decisions (evaluated at tick time)
    wire bass_rest_comb   = (lfsr12[7:4] < rest_threshold);
    wire melody_rest_comb = (lfsr5[3:0] < rest_threshold);

    // =========================================================
    // Musical Shaping: Note Hold
    //
    // On each tick, decide whether to sustain the current note
    // or advance to a new one. When 2 specific bits are both 1
    // (~25% probability), the voice holds its current note.
    // =========================================================
    wire bass_hold_comb   = (lfsr12[11:10] == 2'b11);
    wire melody_hold_comb = (lfsr7[5:4] == 2'b11);

    // =========================================================
    // Registered rest/hold outputs
    // Only update on the respective composition tick.
    // Stay stable between ticks so downstream logic sees a
    // consistent state for the entire note duration.
    // =========================================================
    reg bass_rest_reg, melody_rest_reg;
    reg bass_hold_reg, melody_hold_reg;

    always @(posedge clk) begin
        if (!rst_n) begin
            bass_rest_reg   <= 1'b0;
            melody_rest_reg <= 1'b0;
            bass_hold_reg   <= 1'b0;
            melody_hold_reg <= 1'b0;
        end else if (ena) begin
            if (comp_tick_bass) begin
                bass_rest_reg <= bass_rest_comb;
                bass_hold_reg <= bass_hold_comb;
            end
            if (comp_tick_melody) begin
                melody_rest_reg <= melody_rest_comb;
                melody_hold_reg <= melody_hold_comb;
            end
        end
    end

    assign bass_rest   = bass_rest_reg;
    assign melody_rest = melody_rest_reg;
    assign bass_hold   = bass_hold_reg;
    assign melody_hold = melody_hold_reg;

    // =========================================================
    // Registered note outputs with hold support
    //
    // When hold is active, the raw note keeps its previous value
    // (voice sustains the same pitch). When hold is inactive,
    // the note updates to the current LFSR-derived value.
    // =========================================================
    reg [3:0] bass_raw_reg, melody_raw_reg;

    always @(posedge clk) begin
        if (!rst_n) begin
            bass_raw_reg   <= 4'b0;
            melody_raw_reg <= 4'b0;
        end else if (ena) begin
            // Bass note: update on bass tick unless holding
            if (comp_tick_bass && !bass_hold_comb)
                bass_raw_reg <= lfsr12[3:0];
            // Melody note: update on melody tick unless holding
            if (comp_tick_melody && !melody_hold_comb)
                melody_raw_reg <= lfsr5[3:0] ^ lfsr7[3:0];
        end
    end

    assign bass_raw   = bass_raw_reg;
    assign melody_raw = melody_raw_reg;

endmodule
