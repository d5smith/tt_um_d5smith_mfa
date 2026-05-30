"""
test_clock_divider.py - Required unit tests for clock_divider module

Verifies:
  1. Tick fires at correct interval for various divisor values
  2. Tick is exactly one clock cycle wide
  3. Reset clears counter and suppresses tick
  4. Enable gating freezes counter (pause/resume behavior)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge, ReadOnly


async def sample_edge(dut):
    """Wait for a rising clock edge, then sample after registered updates settle."""
    await RisingEdge(dut.clk)
    await ReadOnly()


async def wait_for_tick(dut, max_cycles=100):
    """Return the number of sampled rising edges until tick is observed HIGH."""
    for cycles in range(1, max_cycles + 1):
        await sample_edge(dut)
        if dut.tick.value == 1:
            return cycles
    raise AssertionError(f"Tick did not fire within {max_cycles} cycles")


async def reset_dut(dut):
    """Apply reset for 5 cycles, then release.

    Reset is released on a falling edge so the next rising edge is the
    first enabled counting edge. No counter advance occurs before this
    helper returns.
    """
    dut.rst_n.value = 0
    dut.ena.value = 1
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


@cocotb.test()
async def test_tick_interval(dut):
    """Tick should fire every `divisor` clock cycles."""

    clock = Clock(dut.clk, 10, units="ns")  # 100 MHz for fast sim
    cocotb.start_soon(clock.start())

    dut.divisor.value = 10
    await reset_dut(dut)

    cycles_to_tick = await wait_for_tick(dut, max_cycles=50)

    assert cycles_to_tick == 10, \
        f"Expected first tick at cycle 10, got cycle {cycles_to_tick}"

    dut._log.info(f"PASS: First tick at cycle {cycles_to_tick} (divisor=10)")

    # Wait for second tick to confirm periodicity (full divisor cycles)
    cycles_to_tick = await wait_for_tick(dut, max_cycles=50)

    assert cycles_to_tick == 10, \
        f"Expected tick period of 10 cycles, got {cycles_to_tick}"

    dut._log.info(f"PASS: Tick period = {cycles_to_tick} cycles")


@cocotb.test()
async def test_tick_one_cycle_wide(dut):
    """Tick must be HIGH for exactly one clock cycle."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.divisor.value = 5
    await reset_dut(dut)

    # Wait for a tick
    await wait_for_tick(dut, max_cycles=50)

    # Tick is HIGH now — check it goes LOW on the very next cycle
    await sample_edge(dut)
    assert dut.tick.value == 0, "Tick was HIGH for more than one cycle"

    dut._log.info("PASS: Tick is exactly one cycle wide")


@cocotb.test()
async def test_reset_clears_counter(dut):
    """Asserting reset mid-count should restart the tick timing."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.divisor.value = 20
    await reset_dut(dut)

    # Let counter run for 8 cycles (less than divisor)
    await ClockCycles(dut.clk, 8)
    assert dut.tick.value == 0, "Tick fired too early"

    # Assert reset mid-count
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    # Now count cycles to next tick — should be a full divisor interval.
    cycles_to_tick = await wait_for_tick(dut, max_cycles=50)

    assert cycles_to_tick == 20, \
        f"After reset, expected tick at cycle 20, got {cycles_to_tick}"

    dut._log.info(f"PASS: Reset restarts counter (tick at cycle {cycles_to_tick})")


@cocotb.test()
async def test_enable_freezes_counter(dut):
    """Disabling should freeze the counter; re-enabling resumes from where it left off."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.divisor.value = 10
    await reset_dut(dut)

    # Let counter run for 5 sampled rising edges (counter advances 0→5).
    for _ in range(5):
        await sample_edge(dut)
    assert dut.tick.value == 0, "Tick fired too early"

    # Disable for 20 cycles (counter should freeze at 5)
    await FallingEdge(dut.clk)
    dut.ena.value = 0
    for _ in range(20):
        await sample_edge(dut)
        assert dut.tick.value == 0, "Tick fired while disabled"

    # Re-enable — counter resumes from 5. It needs 5 more enabled edges
    # to produce a divisor=10 tick.
    await FallingEdge(dut.clk)
    dut.ena.value = 1

    cycles_to_tick = await wait_for_tick(dut, max_cycles=50)

    assert cycles_to_tick == 5, \
        f"After resume, expected tick in 5 cycles, got {cycles_to_tick}"

    dut._log.info(f"PASS: Counter resumed correctly (tick {cycles_to_tick} cycles after re-enable)")


@cocotb.test()
async def test_divisor_2(dut):
    """Edge case: divisor=2 should tick every 2 cycles."""

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.divisor.value = 2
    await reset_dut(dut)

    cycles_to_tick = await wait_for_tick(dut, max_cycles=20)

    assert cycles_to_tick == 2, \
        f"Divisor=2: expected first tick at cycle 2, got {cycles_to_tick}"

    # Second tick: exactly 2 cycles later (full period)
    cycles_to_tick = await wait_for_tick(dut, max_cycles=20)

    assert cycles_to_tick == 2, \
        f"Divisor=2: expected period of 2, got {cycles_to_tick}"

    dut._log.info("PASS: Divisor=2 works correctly")
