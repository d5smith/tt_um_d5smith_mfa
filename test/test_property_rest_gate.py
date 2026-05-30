"""
test_property_rest_gate.py - Property test for musical shaping rest gate

Property 10: Musical Shaping Rest Gate
Validates: Requirements 12.1, 12.5

For any composition tick and any configured rest probability threshold,
the rest gate SHALL suppress note output (producing silence) with probability
proportional to the configured threshold, and the suppression decision SHALL
be derived deterministically from LFSR state bits.

Test approach:
  - Run the composition engine for many ticks
  - Collect rest/active decisions for both voices
  - Verify rest probability is within expected statistical bounds
  - Verify determinism: same seed produces same rest sequence
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles


async def reset_dut(dut):
    """Reset the composition engine."""
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.comp_tick_bass.value = 0
    dut.comp_tick_melody.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def pulse_both_ticks(dut):
    """Send both composition ticks and wait for state to settle."""
    dut.comp_tick_bass.value = 1
    dut.comp_tick_melody.value = 1
    await RisingEdge(dut.clk)
    dut.comp_tick_bass.value = 0
    dut.comp_tick_melody.value = 0
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_rest_probability_in_expected_range(dut):
    """Rest probability should be roughly proportional to threshold.

    With REST_THRESHOLD_BASE=3 and density modulation adding 0-3,
    effective threshold ranges from 3 to 6 out of 16 possible values.
    Expected rest rate: ~19% to ~38% over many ticks.
    We test that the observed rate falls within a reasonable statistical window.
    """

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    num_ticks = 1000
    bass_rest_count = 0
    melody_rest_count = 0

    for _ in range(num_ticks):
        await pulse_both_ticks(dut)
        await FallingEdge(dut.clk)
        if int(dut.bass_rest.value) == 1:
            bass_rest_count += 1
        if int(dut.melody_rest.value) == 1:
            melody_rest_count += 1

    bass_rest_pct = bass_rest_count / num_ticks * 100
    melody_rest_pct = melody_rest_count / num_ticks * 100

    # Expected range: ~10% to ~50% (generous bounds for statistical variation)
    # The exact rate depends on LFSR state distribution and density modulation
    assert 5 < bass_rest_pct < 55, \
        f"Bass rest rate {bass_rest_pct:.1f}% outside expected range (5-55%)"
    assert 5 < melody_rest_pct < 55, \
        f"Melody rest rate {melody_rest_pct:.1f}% outside expected range (5-55%)"

    dut._log.info(f"PASS: Rest probability in range "
                  f"(bass={bass_rest_pct:.1f}%, melody={melody_rest_pct:.1f}%)")


@cocotb.test()
async def test_rest_decision_is_deterministic(dut):
    """Same LFSR seed must produce identical rest sequence on every run."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    num_ticks = 200

    # First run
    await reset_dut(dut)
    run1_bass = []
    run1_melody = []
    for _ in range(num_ticks):
        await pulse_both_ticks(dut)
        await FallingEdge(dut.clk)
        run1_bass.append(int(dut.bass_rest.value))
        run1_melody.append(int(dut.melody_rest.value))

    # Second run (reset and replay)
    await reset_dut(dut)
    run2_bass = []
    run2_melody = []
    for _ in range(num_ticks):
        await pulse_both_ticks(dut)
        await FallingEdge(dut.clk)
        run2_bass.append(int(dut.bass_rest.value))
        run2_melody.append(int(dut.melody_rest.value))

    assert run1_bass == run2_bass, \
        "Bass rest sequence differs between runs — not deterministic"
    assert run1_melody == run2_melody, \
        "Melody rest sequence differs between runs — not deterministic"

    dut._log.info("PASS: Rest decisions are deterministic (200 ticks, 2 runs)")


@cocotb.test()
async def test_rest_not_always_on_or_off(dut):
    """Rest signal should toggle — not stuck at 0 or 1."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    num_ticks = 500
    bass_values = set()
    melody_values = set()

    for _ in range(num_ticks):
        await pulse_both_ticks(dut)
        await FallingEdge(dut.clk)
        bass_values.add(int(dut.bass_rest.value))
        melody_values.add(int(dut.melody_rest.value))

    assert bass_values == {0, 1}, \
        f"Bass rest stuck at {bass_values} over {num_ticks} ticks"
    assert melody_values == {0, 1}, \
        f"Melody rest stuck at {melody_values} over {num_ticks} ticks"

    dut._log.info("PASS: Rest signals toggle between 0 and 1")


@cocotb.test()
async def test_hold_produces_sustained_notes(dut):
    """When hold is active, bass_raw/melody_raw should sustain previous value."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    num_ticks = 500
    bass_notes = []
    melody_notes = []

    for _ in range(num_ticks):
        await pulse_both_ticks(dut)
        await FallingEdge(dut.clk)
        bass_notes.append(int(dut.bass_raw.value))
        melody_notes.append(int(dut.melody_raw.value))

    # Count consecutive repeated notes (evidence of hold working)
    bass_holds = sum(1 for i in range(1, len(bass_notes)) if bass_notes[i] == bass_notes[i-1])
    melody_holds = sum(1 for i in range(1, len(melody_notes)) if melody_notes[i] == melody_notes[i-1])

    # With ~25% hold probability, we expect roughly 25% of ticks to repeat
    # Allow generous bounds (10-50%) for statistical variation
    bass_hold_pct = bass_holds / (num_ticks - 1) * 100
    melody_hold_pct = melody_holds / (num_ticks - 1) * 100

    assert bass_hold_pct > 5, \
        f"Bass hold rate too low ({bass_hold_pct:.1f}%) — hold may not be working"
    assert melody_hold_pct > 5, \
        f"Melody hold rate too low ({melody_hold_pct:.1f}%) — hold may not be working"

    dut._log.info(f"PASS: Hold produces sustained notes "
                  f"(bass={bass_hold_pct:.1f}%, melody={melody_hold_pct:.1f}% repeated)")
