<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

--->

## How it works

This chip generates evolving ambient music autonomously using a pipeline of pseudo-random composition, musical scale quantization, and digital sound synthesis.

**Architecture:** LFSR Composition Engine → Scale Quantizer LUT → DDS Sound Engine → PWM/DAC Output

Three Linear Feedback Shift Registers (5-bit, 7-bit, 12-bit) with co-prime maximal-length periods produce pseudo-random sequences that phase against each other, creating melodies that take ~46 days to repeat. A combinational scale quantizer maps raw values to pentatonic, minor 7th, or blues scale tones. Two DDS oscillators (bass drone + melody) generate audio waveforms mixed to a 4-bit parallel DAC output and a single-pin PWM output.

## How to test

1. Connect an R2R resistor ladder to `uo_out[3:0]` for analog audio output, OR
2. Connect `uio_out[0]` (PWM) through a simple RC low-pass filter to headphones
3. Apply 25 MHz clock
4. Assert reset (rst_n LOW), then release
5. Music begins playing automatically
6. Use `ui_in[1:0]` to select scale (00=pentatonic, 01=minor7, 10=blues)
7. Use `ui_in[3:2]` to select tempo (00=slow, 01=medium, 10=fast, 11=very fast)
8. Use `ui_in[5:4]` and `ui_in[7:6]` to select bass/melody waveforms

## External hardware

- 4-bit R2R DAC ladder on `uo_out[3:0]` (4x 10kΩ, 4x 20kΩ resistors)
- OR: RC low-pass filter on `uio_out[0]` (10kΩ + 100nF → headphone jack)
- Optional: LEDs on `uo_out[7:4]` for debug visibility
