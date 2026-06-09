![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# Music for ASICs

Music for ASICs is a Tiny Tapeout GF180 digital design that generates ambient music directly in hardware. It combines pseudo-random composition, scale quantization, and direct digital synthesis to produce an evolving two-voice audio stream with no CPU, firmware, memory, or external sequencer.

The design targets the TTGF26b shuttle and occupies a `1x2` tile area.

## What it does

The chip runs from the Tiny Tapeout 25 MHz system clock. Three maximal-length LFSRs create deterministic pseudo-random musical events, which are mapped onto selectable scales and played by two DDS voices:

- Bass voice: lower-register drone and pulse patterns.
- Melody voice: faster note stream layered above the bass.
- Scale quantizer: pentatonic, minor 7th, blues, or fallback mapping.
- Waveform selection: square, triangle, or sawtooth per voice.
- Audio output: 4-bit parallel DAC on `uo_out[3:0]` and PWM audio on `uio_out[0]`.

The result is deterministic after reset, but the combined LFSR periods make the phrase evolution long enough to feel non-repeating in normal use.

## Pinout

### Inputs

| Pin | Function |
| --- | --- |
| `ui_in[1:0]` | Scale select: `00` pentatonic, `01` minor 7th, `10` blues, `11` fallback |
| `ui_in[3:2]` | Tempo select: `00` slow, `01` medium, `10` fast, `11` very fast |
| `ui_in[5:4]` | Bass waveform: `00`/`11` square, `01` triangle, `10` sawtooth |
| `ui_in[7:6]` | Melody waveform: `00`/`11` square, `01` triangle, `10` sawtooth |

### Outputs

| Pin | Function |
| --- | --- |
| `uo_out[3:0]` | 4-bit DAC output, LSB on bit 0 |
| `uo_out[4]` | Debug: sample tick |
| `uo_out[5]` | Debug: bass active |
| `uo_out[6]` | Debug: melody active |
| `uo_out[7]` | Debug: LFSR-12 MSB |
| `uio_out[0]` | PWM audio output |
| `uio_out[7:1]` | Unused, driven low |
| `uio_oe` | `8'b0000_0001`; only `uio[0]` is driven |

## Audio hookup

Use one of these output paths:

- Build a 4-bit R-2R ladder on `uo_out[3:0]` for the DAC output.
- Low-pass filter `uio_out[0]` for PWM audio, for example with an RC filter before a high-impedance audio input or amplifier.

Do not drive low-impedance headphones directly from a GPIO pin. Use an amplifier or a high-impedance input stage.

## Implementation

The top-level module is [src/tt_um_d5smith_mfa.v](src/tt_um_d5smith_mfa.v). The design is split into small synchronous blocks:

- [src/clock_divider.v](src/clock_divider.v): sample-rate and composition ticks.
- [src/composition_engine.v](src/composition_engine.v): LFSR-driven note, hold, and rest generation.
- [src/scale_quantizer.v](src/scale_quantizer.v): raw note to tuning-word mapping.
- [src/sound_engine.v](src/sound_engine.v): DDS oscillators, envelopes, mixer, DAC, and PWM.

Input configuration pins pass through a two-flop synchronizer. Output pins are registered at the Tiny Tapeout boundary to keep timing paths short and predictable.

## Verification

The repository includes cocotb tests for the top-level behavior and focused unit tests for the main blocks. The GitHub Actions flow builds the GDS, runs precheck, and runs gate-level testing for the submitted configuration.

To run the default RTL test locally:

```sh
cd test
make clean
make
```

Local simulation requires Icarus Verilog and the Python packages in [test/requirements.txt](test/requirements.txt).

## Tiny Tapeout metadata

Project metadata, source-file ordering, clock frequency, tile count, and pin names are defined in [info.yaml](info.yaml). The generated Tiny Tapeout datasheet text lives in [docs/info.md](docs/info.md).
