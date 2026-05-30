"""
test_composition_engine.py - Required tests for LFSR composition engine

Verifies:
  1. Each LFSR has the correct maximal-length period (31, 127, 4095)
  2. Reset loads predefined seed values
  3. Deterministic replay: same sequence after reset
  4. Combined period exceeds 24 hours at 4 Hz tick rate
  5. Voice routing outputs are non-zero and change
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from math import lcm


# Expected seeds (must match Verilog localparams)
SEED5 = 0b10011       # 19
SEED7 = 0b1100101     # 101
SEED12 = 0b1010_0011_0111  # 2615


async def sample_edge(dut):
    """Wait for a rising clock edge, then sample after registered updates settle."""
    await RisingEdge(dut.clk)
    await ReadOnly()


async def reset_dut(dut):
    """Reset the composition engine."""
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.comp_tick_bass.value = 0
    dut.comp_tick_melody.value = 0
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await sample_edge(dut)


async def pulse_melody_tick(dut):
    """Send a single-cycle melody tick pulse and wait for state to update."""
    await FallingEdge(dut.clk)
    dut.comp_tick_melody.value = 1
    await sample_edge(dut)
    await FallingEdge(dut.clk)
    dut.comp_tick_melody.value = 0


async def pulse_bass_tick(dut):
    """Send a single-cycle bass tick pulse and wait for state to update."""
    await FallingEdge(dut.clk)
    dut.comp_tick_bass.value = 1
    await sample_edge(dut)
    await FallingEdge(dut.clk)
    dut.comp_tick_bass.value = 0


async def pulse_both_ticks(dut):
    """Send both ticks simultaneously and wait for state to update."""
    await FallingEdge(dut.clk)
    dut.comp_tick_bass.value = 1
    dut.comp_tick_melody.value = 1
    await sample_edge(dut)
    await FallingEdge(dut.clk)
    dut.comp_tick_bass.value = 0
    dut.comp_tick_melody.value = 0


@cocotb.test()
async def test_reset_loads_seeds(dut):
    """After reset, all LFSRs should contain their predefined seed values."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    assert dut.lfsr5_out.value == SEED5, \
        f"LFSR-5 seed: expected {SEED5}, got {dut.lfsr5_out.value}"
    assert dut.lfsr7_out.value == SEED7, \
        f"LFSR-7 seed: expected {SEED7}, got {dut.lfsr7_out.value}"
    assert dut.lfsr12_out.value == SEED12, \
        f"LFSR-12 seed: expected {SEED12}, got {dut.lfsr12_out.value}"

    dut._log.info("PASS: All LFSRs loaded with correct seeds after reset")


@cocotb.test()
async def test_lfsr5_period(dut):
    """LFSR-5 should visit all 31 non-zero states and return to seed."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    visited = set()
    visited.add(int(dut.lfsr5_out.value))

    for i in range(31):
        await pulse_melody_tick(dut)
        state = int(dut.lfsr5_out.value)
        if i < 30:  # Steps 0-29: should be new states
            assert state not in visited, \
                f"LFSR-5 revisited state {state} at step {i+1}"
        visited.add(state)

    # After 31 steps, should be back to seed
    assert int(dut.lfsr5_out.value) == SEED5, \
        f"LFSR-5 did not return to seed after 31 steps, got {int(dut.lfsr5_out.value)}"

    # Should have visited exactly 31 unique states
    assert len(visited) == 31, \
        f"LFSR-5 visited {len(visited)} states, expected 31"

    # Verify no zero state was visited
    assert 0 not in visited, "LFSR-5 visited the all-zero state"

    dut._log.info("PASS: LFSR-5 has maximal period of 31")


@cocotb.test()
async def test_lfsr7_period(dut):
    """LFSR-7 should visit all 127 non-zero states and return to seed."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    visited = set()
    visited.add(int(dut.lfsr7_out.value))

    for i in range(127):
        await pulse_melody_tick(dut)
        state = int(dut.lfsr7_out.value)
        visited.add(state)

    # After 127 steps, should be back to seed
    assert int(dut.lfsr7_out.value) == SEED7, \
        f"LFSR-7 did not return to seed after 127 steps, got {int(dut.lfsr7_out.value)}"

    assert len(visited) == 127, \
        f"LFSR-7 visited {len(visited)} states, expected 127"

    assert 0 not in visited, "LFSR-7 visited the all-zero state"

    dut._log.info("PASS: LFSR-7 has maximal period of 127")


@cocotb.test()
async def test_lfsr12_period(dut):
    """LFSR-12 should visit all 4095 non-zero states and return to seed."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    visited = set()
    visited.add(int(dut.lfsr12_out.value))

    for i in range(4095):
        await pulse_bass_tick(dut)
        state = int(dut.lfsr12_out.value)
        visited.add(state)

    # After 4095 steps, should be back to seed
    assert int(dut.lfsr12_out.value) == SEED12, \
        f"LFSR-12 did not return to seed after 4095 steps, got {int(dut.lfsr12_out.value)}"

    assert len(visited) == 4095, \
        f"LFSR-12 visited {len(visited)} states, expected 4095"

    assert 0 not in visited, "LFSR-12 visited the all-zero state"

    dut._log.info("PASS: LFSR-12 has maximal period of 4095")


@cocotb.test()
async def test_deterministic_replay(dut):
    """Same seed + same ticks = identical sequence every time."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # First run: collect 50 states
    await reset_dut(dut)
    run1 = []
    for _ in range(50):
        await pulse_both_ticks(dut)
        run1.append((
            int(dut.lfsr5_out.value),
            int(dut.lfsr7_out.value),
            int(dut.lfsr12_out.value),
        ))

    # Reset and run again
    await reset_dut(dut)
    run2 = []
    for _ in range(50):
        await pulse_both_ticks(dut)
        run2.append((
            int(dut.lfsr5_out.value),
            int(dut.lfsr7_out.value),
            int(dut.lfsr12_out.value),
        ))

    assert run1 == run2, "LFSR sequences differ after reset — not deterministic"

    dut._log.info("PASS: Deterministic replay confirmed (50 ticks)")


@cocotb.test()
async def test_combined_period_exceeds_24h(dut):
    """LCM(31, 127, 4095) at 4 Hz must exceed 24 hours."""

    # This is a pure math test — no simulation needed
    period = lcm(31, lcm(127, 4095))
    hours = period / 4 / 3600  # 4 Hz tick rate

    assert period == 16_122_015, f"Expected LCM=16122015, got {period}"
    assert hours > 24, f"Combined period is only {hours:.1f} hours, need >24"

    dut._log.info(f"PASS: Combined period = {period} ticks = {hours:.1f} hours at 4 Hz")


@cocotb.test()
async def test_voice_routing(dut):
    """bass_raw and melody_raw should produce changing values."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    bass_values = set()
    melody_values = set()

    for _ in range(100):
        await pulse_both_ticks(dut)
        bass_values.add(int(dut.bass_raw.value))
        melody_values.add(int(dut.melody_raw.value))

    # Over 100 ticks, we should see multiple distinct values (not stuck)
    assert len(bass_values) > 5, \
        f"bass_raw only produced {len(bass_values)} unique values in 100 ticks"
    assert len(melody_values) > 5, \
        f"melody_raw only produced {len(melody_values)} unique values in 100 ticks"

    dut._log.info(f"PASS: Voice routing active (bass: {len(bass_values)} values, melody: {len(melody_values)} values)")
