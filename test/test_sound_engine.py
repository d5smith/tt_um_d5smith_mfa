"""
test_sound_engine.py - Required tests for sound engine (Tasks 5 + 8)

Tests are structured to verify each layer independently:
  1. Phase accumulators (bass + melody) — direct register access
  2. Waveform generation (bass + melody) — direct sample access
  3. Mixer — verifies (bass>>1) + (melody>>1) with no overflow
  4. PWM duty cycle — proportional to mixed output
  5. DAC output — top 4 bits of mixed output
  6. Reset behavior
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge


async def reset_dut(dut):
    """Reset the sound engine."""
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.sample_tick.value = 0
    dut.tuning_word_bass.value = 0
    dut.tuning_word_melody.value = 0
    dut.waveform_bass.value = 0
    dut.waveform_melody.value = 0
    dut.bass_active.value = 1
    dut.melody_active.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def pulse_sample_tick(dut):
    """Send a single-cycle sample tick and wait for state to update."""
    dut.sample_tick.value = 1
    await RisingEdge(dut.clk)
    dut.sample_tick.value = 0
    await RisingEdge(dut.clk)


# =========================================================
# Phase Accumulator Tests (direct register access)
# =========================================================

@cocotb.test()
async def test_bass_accumulator_increment(dut):
    """Bass phase accumulator increments by tuning_word_bass on each sample tick."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    tuning_word = 1802  # A4
    dut.tuning_word_bass.value = tuning_word

    expected_acc = 0
    for i in range(10):
        await pulse_sample_tick(dut)
        expected_acc = (expected_acc + tuning_word) & 0xFFFF
        await FallingEdge(dut.clk)
        actual_acc = int(dut.dut.phase_acc_bass.value)
        assert actual_acc == expected_acc, \
            f"Bass acc step {i+1}: expected {expected_acc}, got {actual_acc}"

    dut._log.info("PASS: Bass phase accumulator increments correctly")


@cocotb.test()
async def test_melody_accumulator_increment(dut):
    """Melody phase accumulator increments by tuning_word_melody on each sample tick."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    tuning_word = 1073  # C4
    dut.tuning_word_melody.value = tuning_word

    expected_acc = 0
    for i in range(10):
        await pulse_sample_tick(dut)
        expected_acc = (expected_acc + tuning_word) & 0xFFFF
        await FallingEdge(dut.clk)
        actual_acc = int(dut.dut.phase_acc_melody.value)
        assert actual_acc == expected_acc, \
            f"Melody acc step {i+1}: expected {expected_acc}, got {actual_acc}"

    dut._log.info("PASS: Melody phase accumulator increments correctly")


@cocotb.test()
async def test_accumulator_wraps(dut):
    """Both accumulators wrap naturally at 16-bit boundary."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    tuning_word = 4095
    dut.tuning_word_bass.value = tuning_word
    dut.tuning_word_melody.value = tuning_word

    expected_acc = 0
    for i in range(20):
        await pulse_sample_tick(dut)
        expected_acc = (expected_acc + tuning_word) & 0xFFFF
        await FallingEdge(dut.clk)
        bass_acc = int(dut.dut.phase_acc_bass.value)
        melody_acc = int(dut.dut.phase_acc_melody.value)
        assert bass_acc == expected_acc, \
            f"Bass wrap step {i+1}: expected {expected_acc}, got {bass_acc}"
        assert melody_acc == expected_acc, \
            f"Melody wrap step {i+1}: expected {expected_acc}, got {melody_acc}"

    dut._log.info("PASS: Both accumulators wrap correctly at 16-bit boundary")


# =========================================================
# Waveform Generation Tests (direct sample access)
# =========================================================

@cocotb.test()
async def test_bass_square_wave(dut):
    """Bass square wave outputs 0 or 255 based on accumulator MSB."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.tuning_word_bass.value = 2048  # Half-period in 32 ticks
    dut.waveform_bass.value = 0  # Square

    samples = []
    for _ in range(64):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        samples.append(int(dut.dut.bass_sample.value))

    unique = set(samples)
    assert unique == {0, 255}, f"Bass square wave unexpected values: {unique}"
    assert abs(samples.count(0) - samples.count(255)) <= 2, "Asymmetric square wave"

    dut._log.info("PASS: Bass square wave produces only 0 and 255")


@cocotb.test()
async def test_melody_sawtooth_wave(dut):
    """Melody sawtooth outputs phase_acc_melody[15:8] directly."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    tuning_word = 1802
    dut.tuning_word_melody.value = tuning_word
    dut.waveform_melody.value = 2  # Sawtooth

    expected_acc = 0
    for i in range(10):
        await pulse_sample_tick(dut)
        expected_acc = (expected_acc + tuning_word) & 0xFFFF
        await FallingEdge(dut.clk)
        expected_sample = (expected_acc >> 8) & 0xFF
        actual_sample = int(dut.dut.melody_sample.value)
        assert actual_sample == expected_sample, \
            f"Melody sawtooth step {i+1}: expected {expected_sample}, got {actual_sample}"

    dut._log.info("PASS: Melody sawtooth outputs phase_acc[15:8] correctly")


# =========================================================
# Mixer Tests
# =========================================================

@cocotb.test()
async def test_mixer_no_overflow(dut):
    """Mixer output should never exceed 255, even with both voices at full amplitude."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Set both voices to square wave
    dut.tuning_word_bass.value = 2048
    dut.tuning_word_melody.value = 2048
    dut.waveform_bass.value = 0
    dut.waveform_melody.value = 0
    dut.bass_active.value = 1
    dut.melody_active.value = 1

    # Wait for amplitude to ramp to full (32 sample ticks with SLEW_STEP=8)
    for _ in range(40):
        await pulse_sample_tick(dut)

    # Now both amplitudes should be at 255 — verify mixer doesn't overflow
    for _ in range(64):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        mixed = int(dut.mixed_sample_int.value)
        assert mixed <= 255, f"Mixer overflow: {mixed}"

    dut._log.info("PASS: Mixer never overflows with both voices at full amplitude")


@cocotb.test()
async def test_mixer_solo_voice_full_amplitude(dut):
    """A solo active voice should reach full amplitude after ramp completes."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Solo bass: melody inactive
    dut.tuning_word_bass.value = 2048
    dut.waveform_bass.value = 0  # Square
    dut.bass_active.value = 1
    dut.melody_active.value = 0

    # Wait for amplitude to ramp to full
    for _ in range(40):
        await pulse_sample_tick(dut)

    # Now bass amplitude should be 255 — solo voice at full scale
    await FallingEdge(dut.clk)
    bass_amp = int(dut.dut.bass_amplitude.value)
    assert bass_amp == 255, f"Bass amplitude didn't reach full: {bass_amp}"

    # Verify mixed output matches envelope-scaled bass sample
    # Formula: output = 128 + ((sample - 128) * amplitude) / 256
    for _ in range(32):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        bass_s = int(dut.dut.bass_sample.value)
        mixed = int(dut.mixed_sample_int.value)
        # Expected: 128 + ((bass_s - 128) * 255) / 256
        centered = bass_s - 128  # signed: -128 to +127
        scaled = (centered * 255) // 256  # Python integer division truncates toward negative infinity
        # Verilog arithmetic shift may differ slightly — allow ±1
        expected = 128 + scaled
        assert abs(mixed - expected) <= 1, \
            f"Solo bass: sample={bass_s}, expected ~{expected}, got {mixed}"

    dut._log.info("PASS: Solo voice reaches full amplitude after ramp")


@cocotb.test()
async def test_mixer_silence_is_midscale(dut):
    """When both voices are inactive, mixer outputs mid-scale (128)."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.bass_active.value = 0
    dut.melody_active.value = 0
    dut.tuning_word_bass.value = 2048
    dut.tuning_word_melody.value = 2048

    # Wait for any residual amplitude to ramp down
    for _ in range(40):
        await pulse_sample_tick(dut)

    await FallingEdge(dut.clk)
    mixed = int(dut.mixed_sample_int.value)
    assert mixed == 128, f"Silence: expected 128, got {mixed}"

    dut._log.info("PASS: Both voices inactive produces mid-scale (128)")


@cocotb.test()
async def test_slew_limiter_ramp(dut):
    """Amplitude should ramp up gradually when voice becomes active, and down when inactive."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Start with bass inactive — amplitude should be 0
    dut.bass_active.value = 0
    dut.melody_active.value = 0
    dut.tuning_word_bass.value = 2048
    dut.waveform_bass.value = 0

    for _ in range(5):
        await pulse_sample_tick(dut)

    await FallingEdge(dut.clk)
    assert int(dut.dut.bass_amplitude.value) == 0, "Amplitude should be 0 when inactive"

    # Activate bass — amplitude should ramp up by SLEW_STEP (8) each sample tick
    dut.bass_active.value = 1
    prev_amp = 0
    for i in range(5):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        amp = int(dut.dut.bass_amplitude.value)
        assert amp > prev_amp, f"Tick {i}: amplitude not increasing ({prev_amp} → {amp})"
        assert amp == prev_amp + 8, f"Tick {i}: expected {prev_amp+8}, got {amp}"
        prev_amp = amp

    # After 5 ticks: amplitude should be 40
    assert prev_amp == 40, f"After 5 ramp ticks: expected 40, got {prev_amp}"

    # Deactivate — amplitude should ramp down
    dut.bass_active.value = 0
    for i in range(5):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        amp = int(dut.dut.bass_amplitude.value)
        assert amp < prev_amp, f"Tick {i}: amplitude not decreasing ({prev_amp} → {amp})"
        prev_amp = amp

    # After 5 down ticks from 40: should be 0
    assert prev_amp == 0, f"After ramp down: expected 0, got {prev_amp}"

    dut._log.info("PASS: Slew limiter ramps up and down correctly")


@cocotb.test()
async def test_slew_fades_to_midscale(dut):
    """When a voice deactivates, mixed output should approach 128 (midscale), not 0."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Solo bass, square wave, advance accumulator past midpoint then freeze
    dut.tuning_word_bass.value = 4095
    dut.waveform_bass.value = 0  # Square
    dut.bass_active.value = 1
    dut.melody_active.value = 0

    # Ramp to full amplitude and advance past midpoint (MSB=1 → sample=255)
    for _ in range(50):
        await pulse_sample_tick(dut)

    # Freeze accumulator so sample stays constant during fade
    dut.tuning_word_bass.value = 0

    # Check what sample value we're frozen at
    await pulse_sample_tick(dut)
    await FallingEdge(dut.clk)
    bass_amp = int(dut.dut.bass_amplitude.value)
    bass_s = int(dut.dut.bass_sample.value)
    assert bass_amp == 255, f"Expected full amplitude, got {bass_amp}"

    # Determine if sample is above or below midscale
    above_midscale = (bass_s > 128)

    # Now deactivate — voice should fade toward 128
    dut.bass_active.value = 0

    samples_during_fade = []
    for _ in range(35):  # Enough ticks for full ramp down (255/8 = 32 ticks)
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        samples_during_fade.append(int(dut.mixed_sample_int.value))

    # The fade should approach 128 from whichever side we started
    final_sample = samples_during_fade[-1]
    assert final_sample == 128, \
        f"After full fade, expected 128 (midscale), got {final_sample}"

    # Verify monotonic approach toward 128
    if above_midscale:
        for i, s in enumerate(samples_during_fade):
            assert s >= 128, \
                f"Fade tick {i}: sample {s} fell below midscale 128"
    else:
        for i, s in enumerate(samples_during_fade):
            assert s <= 128, \
                f"Fade tick {i}: sample {s} rose above midscale 128"

    dut._log.info(f"PASS: Voice fades smoothly toward midscale 128 "
                  f"(sample={bass_s}, first={samples_during_fade[0]}, last={final_sample})")


# =========================================================
# PWM and DAC Tests
# =========================================================

@cocotb.test()
async def test_pwm_duty_cycle(dut):
    """PWM HIGH count should be proportional to mixed_sample_int."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Both voices active with square wave, wait for amplitude ramp
    dut.tuning_word_bass.value = 4095
    dut.tuning_word_melody.value = 4095
    dut.waveform_bass.value = 0
    dut.waveform_melody.value = 0
    dut.bass_active.value = 1
    dut.melody_active.value = 1

    # Ramp amplitude to full
    for _ in range(40):
        await pulse_sample_tick(dut)

    # Advance accumulators past midpoint so square wave outputs 255
    for _ in range(9):
        await pulse_sample_tick(dut)

    # Read current mixed value and verify PWM matches it
    await FallingEdge(dut.clk)
    mixed_val = int(dut.mixed_sample_int.value)

    # Count PWM HIGH cycles over one full period
    high_count = 0
    for _ in range(256):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if int(dut.pwm_out.value) == 1:
            high_count += 1

    assert abs(high_count - mixed_val) <= 2, \
        f"PWM with mixed={mixed_val}: expected ~{mixed_val} HIGHs, got {high_count}"

    dut._log.info(f"PASS: PWM duty proportional to mixed sample ({mixed_val}→{high_count} HIGHs)")


@cocotb.test()
async def test_dac_is_top_4_bits(dut):
    """DAC output equals top 4 bits of mixed_sample_int."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.tuning_word_bass.value = 4095
    dut.tuning_word_melody.value = 2048
    dut.waveform_bass.value = 2   # Sawtooth
    dut.waveform_melody.value = 2  # Sawtooth

    for i in range(20):
        await pulse_sample_tick(dut)
        await FallingEdge(dut.clk)
        mixed = int(dut.mixed_sample_int.value)
        dac = int(dut.dac_out.value)
        expected_dac = (mixed >> 4) & 0xF
        assert dac == expected_dac, \
            f"Step {i}: mixed={mixed}, DAC expected {expected_dac}, got {dac}"

    dut._log.info("PASS: DAC output equals top 4 bits of mixed sample")


# =========================================================
# Reset Test
# =========================================================

@cocotb.test()
async def test_reset_clears_state(dut):
    """Reset zeroes accumulators, drives DAC to mid-scale, and PWM to 50% duty."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Advance both accumulators
    dut.tuning_word_bass.value = 2000
    dut.tuning_word_melody.value = 3000
    dut.waveform_bass.value = 2
    dut.waveform_melody.value = 2
    for _ in range(10):
        await pulse_sample_tick(dut)

    # Verify non-zero
    await FallingEdge(dut.clk)
    assert int(dut.dut.phase_acc_bass.value) != 0
    assert int(dut.dut.phase_acc_melody.value) != 0

    # Assert reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    await FallingEdge(dut.clk)

    # DAC should be mid-scale during reset
    assert int(dut.dac_out.value) == 0b1000, \
        f"DAC during reset: expected 8, got {int(dut.dac_out.value)}"

    # PWM should be ~50% duty during reset
    pwm_high = 0
    for _ in range(256):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if int(dut.pwm_out.value) == 1:
            pwm_high += 1
    assert 126 <= pwm_high <= 130, \
        f"PWM during reset: expected ~128 HIGHs (50%), got {pwm_high}"

    # Release reset and verify accumulators are zero
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)

    assert int(dut.dut.phase_acc_bass.value) == 0, "Bass acc not cleared by reset"
    assert int(dut.dut.phase_acc_melody.value) == 0, "Melody acc not cleared by reset"

    dut._log.info("PASS: Reset clears accumulators, DAC mid-scale, PWM 50%")
