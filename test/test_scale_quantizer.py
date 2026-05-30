"""
test_scale_quantizer.py - Required tests for scale quantizer module

Verifies:
  1. Every input combination produces a non-zero tuning word (total function)
  2. scale_sel=11 falls back to pentatonic (same as 00)
  3. Bass tuning word is exactly half of melody tuning word
  4. Pentatonic outputs correspond to correct note frequencies
  5. All scales produce values within valid 12-bit range
"""

import cocotb
from cocotb.triggers import Timer


async def set_inputs(dut, raw_note, scale_sel, is_bass):
    """Set quantizer inputs and wait for combinational propagation."""
    dut.raw_note.value = raw_note
    dut.scale_sel.value = scale_sel
    dut.is_bass.value = is_bass
    await Timer(10, units="ns")  # Combinational settling time


@cocotb.test()
async def test_total_function_all_nonzero(dut):
    """Every possible input must produce a defined, non-zero tuning word."""

    for scale in range(4):
        for note in range(16):
            await set_inputs(dut, note, scale, is_bass=0)
            tw = int(dut.tuning_word.value)
            assert tw != 0, \
                f"Zero tuning word for scale_sel={scale}, raw_note={note}"
            assert tw <= 4095, \
                f"Tuning word exceeds 12 bits: {tw} for scale={scale}, note={note}"

    dut._log.info("PASS: All 64 melody combinations produce non-zero tuning words")


@cocotb.test()
async def test_fallback_matches_pentatonic(dut):
    """scale_sel=11 (reserved) must produce identical output to scale_sel=00 (pentatonic)."""

    for note in range(16):
        # Get pentatonic value
        await set_inputs(dut, note, scale_sel=0, is_bass=0)
        penta_tw = int(dut.tuning_word.value)

        # Get fallback value
        await set_inputs(dut, note, scale_sel=3, is_bass=0)
        fallback_tw = int(dut.tuning_word.value)

        assert penta_tw == fallback_tw, \
            f"Fallback mismatch at note {note}: pentatonic={penta_tw}, fallback={fallback_tw}"

    dut._log.info("PASS: scale_sel=11 falls back to pentatonic correctly")


@cocotb.test()
async def test_bass_is_half_melody(dut):
    """Bass tuning word must be exactly half the melody tuning word (one octave down)."""

    for scale in range(4):
        for note in range(16):
            # Get melody value
            await set_inputs(dut, note, scale, is_bass=0)
            melody_tw = int(dut.tuning_word.value)

            # Get bass value
            await set_inputs(dut, note, scale, is_bass=1)
            bass_tw = int(dut.tuning_word.value)

            expected_bass = melody_tw >> 1  # Integer division by 2
            assert bass_tw == expected_bass, \
                f"Bass mismatch: scale={scale}, note={note}, " \
                f"melody={melody_tw}, bass={bass_tw}, expected={expected_bass}"

    dut._log.info("PASS: All 64 bass values are exactly half their melody counterparts")


@cocotb.test()
async def test_pentatonic_full_table(dut):
    """All 16 pentatonic melody tuning words must match the expected table."""

    # Pentatonic (C): C, D, E, G, A across 2 octaves with wrap
    expected = [
        1073,  # 0:  C4
        1204,  # 1:  D4
        1351,  # 2:  E4
        1606,  # 3:  G4
        1802,  # 4:  A4
        2146,  # 5:  C5
        2408,  # 6:  D5
        2703,  # 7:  E5
        3212,  # 8:  G5
        3604,  # 9:  A5
        1073,  # 10: C4 (wrap)
        1204,  # 11: D4
        1351,  # 12: E4
        1606,  # 13: G4
        1802,  # 14: A4
        2146,  # 15: C5
    ]

    for note in range(16):
        await set_inputs(dut, note, scale_sel=0, is_bass=0)
        actual = int(dut.tuning_word.value)
        assert actual == expected[note], \
            f"Pentatonic note {note}: expected {expected[note]}, got {actual}"

    dut._log.info("PASS: All 16 pentatonic tuning words match expected table")


@cocotb.test()
async def test_minor7_full_table(dut):
    """All 16 minor 7th melody tuning words must match the expected table."""

    # Minor 7th (Am): A, C, E, G starting at octave 3
    expected = [
        901,   # 0:  A3
        1073,  # 1:  C4
        1351,  # 2:  E4
        1606,  # 3:  G4
        1802,  # 4:  A4
        2146,  # 5:  C5
        2703,  # 6:  E5
        3212,  # 7:  G5
        901,   # 8:  A3 (wrap)
        1073,  # 9:  C4
        1351,  # 10: E4
        1606,  # 11: G4
        1802,  # 12: A4
        2146,  # 13: C5
        2703,  # 14: E5
        3212,  # 15: G5
    ]

    for note in range(16):
        await set_inputs(dut, note, scale_sel=1, is_bass=0)
        actual = int(dut.tuning_word.value)
        assert actual == expected[note], \
            f"Minor7 note {note}: expected {expected[note]}, got {actual}"

    dut._log.info("PASS: All 16 minor 7th tuning words match expected table")


@cocotb.test()
async def test_blues_full_table(dut):
    """All 16 blues melody tuning words must match the expected table."""

    # Blues (A): A, C, D, D#, E, G starting at octave 3
    expected = [
        901,   # 0:  A3
        1073,  # 1:  C4
        1204,  # 2:  D4
        1276,  # 3:  D#4
        1351,  # 4:  E4
        1606,  # 5:  G4
        1802,  # 6:  A4
        2146,  # 7:  C5
        2408,  # 8:  D5
        2551,  # 9:  D#5
        2703,  # 10: E5
        3212,  # 11: G5
        901,   # 12: A3 (wrap)
        1073,  # 13: C4
        1204,  # 14: D4
        1276,  # 15: D#4
    ]

    for note in range(16):
        await set_inputs(dut, note, scale_sel=2, is_bass=0)
        actual = int(dut.tuning_word.value)
        assert actual == expected[note], \
            f"Blues note {note}: expected {expected[note]}, got {actual}"

    dut._log.info("PASS: All 16 blues tuning words match expected table")
