/*
 * sound_engine - DDS oscillators, mixer, PWM, DAC output
 *
 * Two-voice DDS with independent phase accumulators and waveform selection.
 * Voices are mixed to a single 8-bit audio sample.
 * Output: 4-bit DAC (top 4 bits), PWM (full 8-bit resolution), debug signals.
 *
 * Waveforms: square (00/11), triangle (01), sawtooth (10).
 * Mixer: (bass >> 1) + (melody >> 1) — guarantees no overflow.
 *
 * Safe-state gating when ena=0 is handled by the top-level wrapper (Task 9),
 * not here. This module always reflects its internal audio state.
 * Only reset forces mid-scale locally (DAC) / 50% (PWM).
 */

module sound_engine (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        ena,
    input  wire        sample_tick,
    input  wire [11:0] tuning_word_bass,
    input  wire [11:0] tuning_word_melody,
    input  wire [1:0]  waveform_bass,
    input  wire [1:0]  waveform_melody,
    input  wire        bass_active,
    input  wire        melody_active,
    output wire [7:0]  mixed_sample_int,
    output wire [3:0]  dac_out,
    output wire [3:0]  debug_out,
    output wire        pwm_out
);

    // =========================================================
    // DDS Phase Accumulators (two voices)
    // =========================================================
    reg [15:0] phase_acc_bass;
    reg [15:0] phase_acc_melody;

    always @(posedge clk) begin
        if (!rst_n) begin
            phase_acc_bass   <= 16'b0;
            phase_acc_melody <= 16'b0;
        end else if (ena && sample_tick) begin
            phase_acc_bass   <= phase_acc_bass   + {4'b0, tuning_word_bass};
            phase_acc_melody <= phase_acc_melody + {4'b0, tuning_word_melody};
        end
    end

    // =========================================================
    // Waveform Generation (bass voice)
    // =========================================================
    reg [7:0] bass_sample;

    always @(*) begin
        case (waveform_bass)
            2'b00, 2'b11: begin
                // Square wave: MSB selects full-scale high or low
                bass_sample = phase_acc_bass[15] ? 8'd255 : 8'd0;
            end
            2'b01: begin
                // Triangle wave: ramp up then fold back down
                if (phase_acc_bass[15])
                    bass_sample = {~phase_acc_bass[14:8], 1'b1};
                else
                    bass_sample = {phase_acc_bass[14:8], 1'b0};
            end
            2'b10: begin
                // Sawtooth wave: top 8 bits directly
                bass_sample = phase_acc_bass[15:8];
            end
            default: bass_sample = 8'd128;
        endcase
    end

    // =========================================================
    // Waveform Generation (melody voice)
    // =========================================================
    reg [7:0] melody_sample;

    always @(*) begin
        case (waveform_melody)
            2'b00, 2'b11: begin
                melody_sample = phase_acc_melody[15] ? 8'd255 : 8'd0;
            end
            2'b01: begin
                if (phase_acc_melody[15])
                    melody_sample = {~phase_acc_melody[14:8], 1'b1};
                else
                    melody_sample = {phase_acc_melody[14:8], 1'b0};
            end
            2'b10: begin
                melody_sample = phase_acc_melody[15:8];
            end
            default: melody_sample = 8'd128;
        endcase
    end

    // =========================================================
    // Slew Limiter / Amplitude Envelope
    //
    // Each voice has an 8-bit amplitude register that ramps:
    //   - UP by SLEW_STEP each sample tick when voice is active
    //   - DOWN by SLEW_STEP each sample tick when voice is resting
    // This eliminates harsh clicks at note transitions.
    //
    // SLEW_STEP=8 at 16 kHz → full ramp in ~2ms (32 ticks)
    // =========================================================
    localparam SLEW_STEP = 8'd8;

    reg [7:0] bass_amplitude;
    reg [7:0] melody_amplitude;

    always @(posedge clk) begin
        if (!rst_n) begin
            bass_amplitude   <= 8'd0;
            melody_amplitude <= 8'd0;
        end else if (ena && sample_tick) begin
            // Bass envelope
            if (bass_active) begin
                // Ramp up, cap at 255
                if (bass_amplitude <= (8'd255 - SLEW_STEP))
                    bass_amplitude <= bass_amplitude + SLEW_STEP;
                else
                    bass_amplitude <= 8'd255;
            end else begin
                // Ramp down, floor at 0
                if (bass_amplitude >= SLEW_STEP)
                    bass_amplitude <= bass_amplitude - SLEW_STEP;
                else
                    bass_amplitude <= 8'd0;
            end

            // Melody envelope
            if (melody_active) begin
                if (melody_amplitude <= (8'd255 - SLEW_STEP))
                    melody_amplitude <= melody_amplitude + SLEW_STEP;
                else
                    melody_amplitude <= 8'd255;
            end else begin
                if (melody_amplitude >= SLEW_STEP)
                    melody_amplitude <= melody_amplitude - SLEW_STEP;
                else
                    melody_amplitude <= 8'd0;
            end
        end
    end

    // Apply envelope: scale waveform around midscale (128)
    // output = 128 + ((sample - 128) * amplitude) / 256
    // This fades toward 128 (silence) rather than toward 0,
    // eliminating clicks at the rest transition.
    wire signed [8:0] bass_centered   = {1'b0, bass_sample}   - 9'sd128;
    wire signed [8:0] melody_centered = {1'b0, melody_sample} - 9'sd128;
    wire signed [17:0] bass_scaled_s   = bass_centered   * $signed({1'b0, bass_amplitude});
    wire signed [17:0] melody_scaled_s = melody_centered * $signed({1'b0, melody_amplitude});
    // Divide by 256 (arithmetic right shift 8) then add midscale
    wire signed [8:0] bass_shifted   = bass_scaled_s[16:8];
    wire signed [8:0] melody_shifted = melody_scaled_s[16:8];
    wire [9:0] bass_env_full   = {1'b0, 9'd128} + {bass_shifted[8], bass_shifted[8:0]};
    wire [9:0] melody_env_full = {1'b0, 9'd128} + {melody_shifted[8], melody_shifted[8:0]};
    wire [7:0] bass_env   = bass_env_full[7:0];
    wire [7:0] melody_env = melody_env_full[7:0];

    // =========================================================
    // Audio Mixer
    // Normalization depends on how many voices are active:
    //   Both active: halve each to prevent overflow (max 127+127=254)
    //   One active: pass through at full amplitude (0-255 range)
    //   Neither active: output mid-scale (128) for silence
    // Uses envelope-shaped samples (not raw waveforms).
    // =========================================================
    wire [7:0] bass_gated   = (bass_amplitude > 0)   ? bass_env   : 8'd0;
    wire [7:0] melody_gated = (melody_amplitude > 0) ? melody_env : 8'd0;

    // Determine if each voice is audibly active (amplitude > 0)
    wire bass_audible   = (bass_amplitude > 0);
    wire melody_audible = (melody_amplitude > 0);

    // Half-sample wires for dual-voice mode
    wire [7:0] bass_half   = {1'b0, bass_gated[7:1]};
    wire [7:0] melody_half = {1'b0, melody_gated[7:1]};

    reg [7:0] mixed;
    always @(*) begin
        case ({bass_audible, melody_audible})
            2'b11:   mixed = bass_half + melody_half;  // Both: halve each, no overflow
            2'b10:   mixed = bass_gated;               // Solo bass: full amplitude
            2'b01:   mixed = melody_gated;             // Solo melody: full amplitude
            default: mixed = 8'd128;                   // Silence: mid-scale
        endcase
    end

    assign mixed_sample_int = mixed;

    // =========================================================
    // 4-bit DAC Output (top 4 bits of mixed audio sample)
    // Safe-state gating when ena=0 is handled by top-level (Task 9).
    // Only reset forces mid-scale locally.
    // =========================================================
    assign dac_out = rst_n ? mixed[7:4] : 4'b1000;

    // =========================================================
    // Debug Output Signals (uo_out[7:4])
    //   bit 0 (uo_out[4]): sample_tick indicator
    //   bit 1 (uo_out[5]): bass voice active
    //   bit 2 (uo_out[6]): melody voice active
    //   bit 3 (uo_out[7]): reserved (driven LOW, Task 9 wires LFSR-12 MSB)
    // Driven LOW during reset per bring-up contract.
    // =========================================================
    assign debug_out = rst_n ? {1'b0, melody_active, bass_active, sample_tick} : 4'b0000;

    // =========================================================
    // PWM Output
    // Free-running 8-bit counter at system clock rate.
    // Output HIGH when counter < mixed audio sample value.
    // =========================================================
    reg [7:0] pwm_counter = 8'b0;  // Initial value for simulation (silicon starts arbitrary — OK)
    reg       pwm_reg = 1'b0;

    always @(posedge clk) begin
        pwm_counter <= pwm_counter + 1'b1;  // Always free-running
        if (!rst_n)
            pwm_reg <= (pwm_counter < 8'd128);  // 50% during reset
        else if (ena)
            pwm_reg <= (pwm_counter < mixed);
        else
            pwm_reg <= (pwm_counter < 8'd128);  // 50% when disabled
    end

    assign pwm_out = pwm_reg;

    // Suppress unused bit warnings
    (* keep = "true" *) wire _unused = &{bass_scaled_s[17], bass_scaled_s[7:0],
                     melody_scaled_s[17], melody_scaled_s[7:0],
                     bass_shifted[8], melody_shifted[8],
                     bass_env_full[9:8], melody_env_full[9:8], 1'b0};

endmodule
