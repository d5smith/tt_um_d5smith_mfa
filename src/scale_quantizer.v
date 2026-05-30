/*
 * scale_quantizer - Musical scale lookup table
 *
 * Maps 4-bit raw note values (0-15) to 12-bit DDS tuning words
 * within the selected musical scale. Pure combinational logic.
 *
 * Mapping strategy: raw_note wraps across 2 octaves using modulo.
 *   scale_degree = raw_note % num_notes_in_scale
 *   octave = (raw_note / num_notes_in_scale) % 2
 *   Octave 1 tuning words are doubled from octave 0.
 *
 * Scales:
 *   00 = Pentatonic (C): C, D, E, G, A (5 notes)
 *   01 = Minor 7th (Am): A, C, E, G (4 notes)
 *   10 = Blues (A): A, C, D, D#, E, G (6 notes)
 *   11 = Fallback → Pentatonic
 *
 * Bass voice (is_bass=1) gets tuning word halved (one octave down).
 *
 * Tuning word formula: tuning_word = (freq_hz * 2^16) / 16000
 * (16-bit phase accumulator, 16 kHz sample rate)
 */

module scale_quantizer (
    input  wire [3:0]  raw_note,
    input  wire [1:0]  scale_sel,
    input  wire        is_bass,
    output wire [11:0] tuning_word
);

    reg [11:0] melody_word;

    always @(*) begin
        case (scale_sel)
            // ===== Pentatonic (C): C, D, E, G, A =====
            // Octave 4 base tuning words, octave 5 = 2x
            2'b00, 2'b11: begin
                case (raw_note)
                    // Octave 4 (inputs 0-4)
                    4'd0:  melody_word = 12'd1073;  // C4  262 Hz
                    4'd1:  melody_word = 12'd1204;  // D4  294 Hz
                    4'd2:  melody_word = 12'd1351;  // E4  330 Hz
                    4'd3:  melody_word = 12'd1606;  // G4  392 Hz
                    4'd4:  melody_word = 12'd1802;  // A4  440 Hz
                    // Octave 5 (inputs 5-9)
                    4'd5:  melody_word = 12'd2146;  // C5  524 Hz
                    4'd6:  melody_word = 12'd2408;  // D5  588 Hz
                    4'd7:  melody_word = 12'd2703;  // E5  660 Hz
                    4'd8:  melody_word = 12'd3212;  // G5  784 Hz
                    4'd9:  melody_word = 12'd3604;  // A5  880 Hz
                    // Wrap back to octave 4 (inputs 10-14)
                    4'd10: melody_word = 12'd1073;  // C4
                    4'd11: melody_word = 12'd1204;  // D4
                    4'd12: melody_word = 12'd1351;  // E4
                    4'd13: melody_word = 12'd1606;  // G4
                    4'd14: melody_word = 12'd1802;  // A4
                    // Wrap to octave 5 (input 15)
                    4'd15: melody_word = 12'd2146;  // C5
                    default: melody_word = 12'd1073; // Safety
                endcase
            end

            // ===== Minor 7th (Am): A, C, E, G =====
            // Starting at A3 to keep all values within 12-bit range
            2'b01: begin
                case (raw_note)
                    // Octave 3 (inputs 0-3)
                    4'd0:  melody_word = 12'd901;   // A3  220 Hz
                    4'd1:  melody_word = 12'd1073;  // C4  262 Hz
                    4'd2:  melody_word = 12'd1351;  // E4  330 Hz
                    4'd3:  melody_word = 12'd1606;  // G4  392 Hz
                    // Octave 4 (inputs 4-7)
                    4'd4:  melody_word = 12'd1802;  // A4  440 Hz
                    4'd5:  melody_word = 12'd2146;  // C5  524 Hz
                    4'd6:  melody_word = 12'd2703;  // E5  660 Hz
                    4'd7:  melody_word = 12'd3212;  // G5  784 Hz
                    // Wrap back to octave 3 (inputs 8-11)
                    4'd8:  melody_word = 12'd901;   // A3
                    4'd9:  melody_word = 12'd1073;  // C4
                    4'd10: melody_word = 12'd1351;  // E4
                    4'd11: melody_word = 12'd1606;  // G4
                    // Wrap to octave 4 (inputs 12-15)
                    4'd12: melody_word = 12'd1802;  // A4
                    4'd13: melody_word = 12'd2146;  // C5
                    4'd14: melody_word = 12'd2703;  // E5
                    4'd15: melody_word = 12'd3212;  // G5
                    default: melody_word = 12'd901;  // Safety
                endcase
            end

            // ===== Blues (A): A, C, D, D#, E, G =====
            // Starting at A3 to keep all values within 12-bit range
            2'b10: begin
                case (raw_note)
                    // Octave 3 (inputs 0-5)
                    4'd0:  melody_word = 12'd901;   // A3   220 Hz
                    4'd1:  melody_word = 12'd1073;  // C4   262 Hz
                    4'd2:  melody_word = 12'd1204;  // D4   294 Hz
                    4'd3:  melody_word = 12'd1276;  // D#4  311 Hz
                    4'd4:  melody_word = 12'd1351;  // E4   330 Hz
                    4'd5:  melody_word = 12'd1606;  // G4   392 Hz
                    // Octave 4 (inputs 6-11)
                    4'd6:  melody_word = 12'd1802;  // A4   440 Hz
                    4'd7:  melody_word = 12'd2146;  // C5   524 Hz
                    4'd8:  melody_word = 12'd2408;  // D5   588 Hz
                    4'd9:  melody_word = 12'd2551;  // D#5  622 Hz
                    4'd10: melody_word = 12'd2703;  // E5   660 Hz
                    4'd11: melody_word = 12'd3212;  // G5   784 Hz
                    // Wrap back to octave 3 (inputs 12-15)
                    4'd12: melody_word = 12'd901;   // A3
                    4'd13: melody_word = 12'd1073;  // C4
                    4'd14: melody_word = 12'd1204;  // D4
                    4'd15: melody_word = 12'd1276;  // D#4
                    default: melody_word = 12'd901;  // Safety
                endcase
            end

            default: melody_word = 12'd1073;  // Should never reach here
        endcase
    end

    // Bass voice = one octave down (halve tuning word)
    assign tuning_word = is_bass ? {1'b0, melody_word[11:1]} : melody_word;

endmodule
