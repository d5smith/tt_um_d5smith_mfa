/*
 * tt_um_d5smith_mfa - Generative Ambient Music ASIC
 * Top-level Tiny Tapeout wrapper
 *
 * Target shuttle: TTGF26b (GlobalFoundries)
 *
 * Pipeline: clock_dividers → composition_engine → scale_quantizers → sound_engine
 *
 * Pin allocation (post-synchronization):
 *   ui_in[1:0] = scale_sel (00=pentatonic, 01=minor7, 10=blues, 11=fallback)
 *   ui_in[3:2] = tempo_sel (00=~2Hz, 01=~5Hz, 10=~10Hz, 11=~20Hz)
 *   ui_in[5:4] = waveform_bass (00/11=square, 01=triangle, 10=sawtooth)
 *   ui_in[7:6] = waveform_melody (00/11=square, 01=triangle, 10=sawtooth)
 *   uo_out[3:0] = 4-bit DAC output (registered)
 *   uo_out[7:4] = debug signals (registered)
 *   uio_out[0]  = PWM audio output (registered)
 *   uio_out[1]  = analog experiment (hardcoded off)
 *   uio_out[7:2] = unused (LOW)
 *   uio_oe = 8'b0000_0001 (only PWM pin is output)
 *
 * Boundary registers:
 *   - Inputs ui_in[7:0] go through a 2-FF synchronizer chain. Configs are
 *     external, asynchronous, and slow (humans flipping switches), so this
 *     prevents metastability and breaks the input timing arc that would
 *     otherwise stretch from a pad through the entire audio synth chain.
 *   - Outputs uo_out[7:0] and uio_out[0] are registered before the pad. This
 *     pipelines the output by one cycle (40 ns at 25 MHz = inaudible at the
 *     16 kHz audio rate) and removes the long combinational paths from STA's
 *     critical path.
 */

module tt_um_d5smith_mfa #(
    // Divisor overrides for testing. Default values are for 25 MHz operation.
    // Tests can instantiate with small values to exercise the full pipeline quickly.
    parameter SAMPLE_DIV = 1562,       // 25 MHz / 16 kHz
    parameter TEMPO_SLOW = 12_500_000, // ~2 Hz
    parameter TEMPO_MED  = 5_000_000,  // ~5 Hz
    parameter TEMPO_FAST = 2_500_000,  // ~10 Hz
    parameter TEMPO_VFAST = 1_250_000  // ~20 Hz
)(
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    // =========================================================
    // Input synchronizers — ui_in[7:0]
    // 2-stage synchronizer chain prevents metastability on async config
    // toggling and removes input-to-internal timing arcs from the critical
    // path. The 2-cycle latency (80 ns at 25 MHz) is irrelevant for human-
    // operated config switches.
    // =========================================================
    reg [7:0] ui_in_meta;
    reg [7:0] ui_in_sync;

    always @(posedge clk) begin
        if (!rst_n) begin
            ui_in_meta <= 8'b0;
            ui_in_sync <= 8'b0;
        end else begin
            ui_in_meta <= ui_in;
            ui_in_sync <= ui_in_meta;
        end
    end

    // =========================================================
    // Configuration extraction from synchronized ui_in
    // =========================================================
    wire [1:0] scale_sel_raw   = ui_in_sync[1:0];
    wire [1:0] tempo_sel       = ui_in_sync[3:2];
    wire [1:0] waveform_bass   = ui_in_sync[5:4];
    wire [1:0] waveform_melody = ui_in_sync[7:6];

    // =========================================================
    // Scale selection deferral
    // New scale only takes effect on the next bass composition tick.
    // This means both voices switch scale simultaneously (bass-synchronized).
    // Melody may play a few notes in the old scale before the bass tick fires,
    // but this produces a smoother musical transition than independent switching.
    // =========================================================
    reg [1:0] scale_sel_deferred;
    wire      comp_tick_bass;

    always @(posedge clk) begin
        if (!rst_n)
            scale_sel_deferred <= 2'b00;  // Default to pentatonic
        else if (comp_tick_bass)
            scale_sel_deferred <= scale_sel_raw;
    end

    // =========================================================
    // Tempo → Divisor lookup
    // At 25 MHz system clock:
    //   00 = ~2 Hz:  divisor = 12,500,000
    //   01 = ~5 Hz:  divisor = 5,000,000
    //   10 = ~10 Hz: divisor = 2,500,000
    //   11 = ~20 Hz: divisor = 1,250,000
    // Bass uses the selected tempo. Melody runs 2x faster.
    // =========================================================
    reg [23:0] bass_divisor;
    reg [23:0] melody_divisor;

    always @(*) begin
        case (tempo_sel)
            2'b00: begin
                bass_divisor   = TEMPO_SLOW;
                melody_divisor = TEMPO_SLOW / 2;
            end
            2'b01: begin
                bass_divisor   = TEMPO_MED;
                melody_divisor = TEMPO_MED / 2;
            end
            2'b10: begin
                bass_divisor   = TEMPO_FAST;
                melody_divisor = TEMPO_FAST / 2;
            end
            2'b11: begin
                bass_divisor   = TEMPO_VFAST;
                melody_divisor = TEMPO_VFAST / 2;
            end
        endcase
    end

    // Sample rate divisor (parameterized for testing)
    localparam [23:0] SAMPLE_DIVISOR = SAMPLE_DIV;

    // =========================================================
    // Clock Dividers
    // =========================================================
    wire comp_tick_melody;
    wire sample_tick;

    clock_divider #(.WIDTH(24)) clk_div_bass (
        .clk     (clk),
        .rst_n   (rst_n),
        .ena     (ena),
        .divisor (bass_divisor),
        .tick    (comp_tick_bass)
    );

    clock_divider #(.WIDTH(24)) clk_div_melody (
        .clk     (clk),
        .rst_n   (rst_n),
        .ena     (ena),
        .divisor (melody_divisor),
        .tick    (comp_tick_melody)
    );

    clock_divider #(.WIDTH(24)) clk_div_sample (
        .clk     (clk),
        .rst_n   (rst_n),
        .ena     (ena),
        .divisor (SAMPLE_DIVISOR),
        .tick    (sample_tick)
    );

    // =========================================================
    // Composition Engine
    // =========================================================
    wire [4:0]  lfsr5_out;
    wire [6:0]  lfsr7_out;
    wire [11:0] lfsr12_out;
    wire [3:0]  bass_raw;
    wire [3:0]  melody_raw;
    wire        bass_rest;
    wire        melody_rest;
    wire        bass_hold;
    wire        melody_hold;

    composition_engine comp_eng (
        .clk              (clk),
        .rst_n            (rst_n),
        .ena              (ena),
        .comp_tick_bass   (comp_tick_bass),
        .comp_tick_melody (comp_tick_melody),
        .lfsr5_out        (lfsr5_out),
        .lfsr7_out        (lfsr7_out),
        .lfsr12_out       (lfsr12_out),
        .bass_raw         (bass_raw),
        .melody_raw       (melody_raw),
        .bass_rest        (bass_rest),
        .melody_rest      (melody_rest),
        .bass_hold        (bass_hold),
        .melody_hold      (melody_hold)
    );

    // =========================================================
    // Voice active signals: active = NOT resting
    // =========================================================
    wire bass_active   = ~bass_rest;
    wire melody_active = ~melody_rest;

    // =========================================================
    // Scale Quantizers (one per voice)
    // =========================================================
    wire [11:0] tuning_word_bass;
    wire [11:0] tuning_word_melody;

    scale_quantizer sq_bass (
        .raw_note   (bass_raw),
        .scale_sel  (scale_sel_deferred),
        .is_bass    (1'b1),
        .tuning_word(tuning_word_bass)
    );

    scale_quantizer sq_melody (
        .raw_note   (melody_raw),
        .scale_sel  (scale_sel_deferred),
        .is_bass    (1'b0),
        .tuning_word(tuning_word_melody)
    );

    // =========================================================
    // Sound Engine
    // =========================================================
    wire [7:0] mixed_sample_int;
    wire [3:0] dac_out_raw;
    wire [3:0] debug_out_raw;
    wire       pwm_out_raw;

    sound_engine snd_eng (
        .clk               (clk),
        .rst_n             (rst_n),
        .ena               (ena),
        .sample_tick       (sample_tick),
        .tuning_word_bass  (tuning_word_bass),
        .tuning_word_melody(tuning_word_melody),
        .waveform_bass     (waveform_bass),
        .waveform_melody   (waveform_melody),
        .bass_active       (bass_active),
        .melody_active     (melody_active),
        .mixed_sample_int  (mixed_sample_int),
        .dac_out           (dac_out_raw),
        .debug_out         (debug_out_raw),
        .pwm_out           (pwm_out_raw)
    );

    // =========================================================
    // Output stage
    //
    // Enable Gating (Task 9.2):
    //   When ena=0: DAC → mid-scale, debug → LOW, PWM → LOW
    //   Internal state is NOT reset (preserves musical position).
    //
    // Boundary registration:
    //   uo_out[7:0] and uio_out[0] are registered. The mux that selects between
    //   live signal and safe-state value happens before the register, so the
    //   register's D input is whatever the pad will drive next cycle. This
    //   removes long combinational paths from the input/internal-register
    //   stages all the way out to the pad and gives STA a clean reg-to-pad arc.
    // =========================================================

    // Debug output: replace bit 3 (reserved) with LFSR-12 MSB for slow-evolution visibility
    wire [3:0] debug_final_pre_reg = {lfsr12_out[11], debug_out_raw[2:0]};

    // Mux next-cycle output values (combinational, feeds the register D input)
    wire [3:0] uo_out_dac_next   = ena              ? dac_out_raw       : 4'b1000;
    wire [3:0] uo_out_debug_next = (ena && rst_n)   ? debug_final_pre_reg : 4'b0000;
    wire       uio_out_pwm_next  = pwm_out_raw;

    reg [7:0] uo_out_reg;
    reg       uio_out_pwm_reg;

    always @(posedge clk) begin
        if (!rst_n) begin
            // Reset to safe-state values that the previous combinational
            // path also produced under reset:
            //   dac        = 4'b1000 (mid-scale)
            //   debug      = 4'b0000 (LOW)
            uo_out_reg <= 8'b0000_1000;  // {debug=0000, dac=1000}
        end else begin
            uo_out_reg <= {uo_out_debug_next, uo_out_dac_next};
        end
    end

    // PWM register intentionally has NO reset gate. The sound engine drives
    // pwm_out_raw at 50% duty during reset already (its internal pwm_compare
    // is forced to 128 under reset, and the free-running pwm_counter still
    // toggles), so sampling it every cycle preserves that 50%-duty behavior
    // at the pad. Adding a reset gate here would force the registered output
    // LOW during reset, producing 0%-duty and breaking the existing safe-
    // state tests. Initial value is unimportant: the first post-reset clock
    // edge captures pwm_out_raw before any consumer reads the pad.
    always @(posedge clk) begin
        uio_out_pwm_reg <= uio_out_pwm_next;
    end

    assign uo_out       = uo_out_reg;
    assign uio_out[0]   = uio_out_pwm_reg;
    assign uio_out[1]   = 1'b0;       // Analog experiment hardcoded off
    assign uio_out[7:2] = 6'b000000;  // Unused

    // Only PWM pin (bit 0) is an output
    assign uio_oe = 8'b0000_0001;

    // Suppress unused signals
    (* keep = "true" *) wire _unused = &{uio_in, lfsr5_out, lfsr7_out, lfsr12_out[10:0],
                     mixed_sample_int, bass_hold, melody_hold,
                     debug_out_raw[3], 1'b0};

endmodule
